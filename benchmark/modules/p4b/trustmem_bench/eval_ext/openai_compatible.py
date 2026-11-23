"""OpenAI-compatible HTTP transport and deterministic tape recording for eval_ext."""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from .budget import AttemptBudget
from .contracts import (
    JsonObject,
    ModelAdapter,
    ModelTurnRequest,
    ModelTurnResponse,
    ToolCall,
    ToolSpec,
)


def canonical_json(data: Any) -> str:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def config_fingerprint(
    *,
    protocol_version: str,
    api_dialect: str,
    model: str,
    temperature: float,
    top_p: float,
    seed: int | None,
    parallel_tool_calls: bool | None,
    extra_body: JsonObject | None = None,
    endpoint_profile: str = "local_openai_compatible",
) -> str:
    """Compute a stable SHA-256 fingerprint over non-secret execution settings."""
    payload = {
        "protocol_version": protocol_version,
        "api_dialect": api_dialect,
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "seed": seed,
        "parallel_tool_calls": parallel_tool_calls,
        "extra_body": extra_body or {},
        "endpoint_profile": endpoint_profile,
    }
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    provider: str = "openai_compatible_local"
    api_key_env: str | None = None
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int | None = 101
    parallel_tool_calls: bool | None = False
    timeout_seconds: float = 180.0
    max_transport_retries: int = 2
    retry_backoff_seconds: float = 1.5
    extra_body: JsonObject = field(default_factory=dict)
    endpoint_profile: str = "local_vllm"
    protocol_version: str = "trustmem/native-audit/v1"

    def fingerprint(self) -> str:
        return config_fingerprint(
            protocol_version=self.protocol_version,
            api_dialect="openai_chat_completions_v1",
            model=self.model,
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
            parallel_tool_calls=self.parallel_tool_calls,
            extra_body=self.extra_body,
            endpoint_profile=self.endpoint_profile,
        )


def _format_tool_spec(spec: ToolSpec) -> JsonObject:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.json_schema,
        },
    }


def _normalize_message(msg: JsonObject) -> JsonObject:
    out = dict(msg)
    content = out.get("content")
    if isinstance(content, (dict, list)):
        out["content"] = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return out


def _extract_usage(raw_usage: Any) -> dict[str, int | None]:
    if not isinstance(raw_usage, dict):
        return {"input_tokens": None, "output_tokens": None, "reasoning_tokens": None}
    inp = raw_usage.get("prompt_tokens", raw_usage.get("input_tokens"))
    out = raw_usage.get("completion_tokens", raw_usage.get("output_tokens"))
    reasoning = raw_usage.get("reasoning_tokens")
    details = raw_usage.get("completion_tokens_details")
    if reasoning is None and isinstance(details, dict):
        reasoning = details.get("reasoning_tokens")
    return {
        "input_tokens": int(inp) if isinstance(inp, int) else None,
        "output_tokens": int(out) if isinstance(out, int) else None,
        "reasoning_tokens": int(reasoning) if isinstance(reasoning, int) else None,
    }


def _extract_tool_calls(message: JsonObject) -> tuple[ToolCall, ...]:
    raw_calls = message.get("tool_calls") or []
    calls: list[ToolCall] = []
    for index, item in enumerate(raw_calls):
        fn = item.get("function") or {}
        call_id = str(item.get("id") or f"call_{index}")
        name = str(fn.get("name") or "")
        raw_args = fn.get("arguments", "")
        if isinstance(raw_args, str):
            arguments_raw = raw_args
        else:
            arguments_raw = json.dumps(raw_args, ensure_ascii=False, sort_keys=True)
        calls.append(ToolCall(call_id=call_id, name=name, arguments_raw=arguments_raw))
    return tuple(calls)


class OpenAICompatibleAdapter:
    """Pure-stdlib OpenAI-compatible /v1/chat/completions adapter (vLLM/SGLang/Ollama).

    Retains the first received completion without re-sampling for better answers.
    Only retries transient HTTP 5xx / transport errors up to max_transport_retries.
    Bypasses system proxies automatically for localhost / 127.0.0.1 endpoints.
    """

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        budget: AttemptBudget | None = None,
        bound_nano_usd: int = 1,
    ):
        self.config = config
        self.budget = budget
        self.bound_nano_usd = bound_nano_usd
        self.last_telemetry: JsonObject = {}

    def _endpoint_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _build_payload(self, request: ModelTurnRequest) -> JsonObject:
        messages: list[JsonObject] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            messages.append(_normalize_message(msg))

        payload: JsonObject = {
            "model": request.model or self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": request.max_output_tokens,
        }
        if self.config.seed is not None:
            payload["seed"] = self.config.seed
        if request.tools:
            payload["tools"] = [_format_tool_spec(spec) for spec in request.tools]
            if request.tool_choice:
                payload["tool_choice"] = request.tool_choice
            if self.config.parallel_tool_calls is not None:
                payload["parallel_tool_calls"] = self.config.parallel_tool_calls
        if self.config.extra_body:
            for key, value in self.config.extra_body.items():
                if key not in payload:
                    payload[key] = value
        return payload

    def _opener(self, url: str):
        host = (urlparse(url).hostname or "").lower()
        if host in {"127.0.0.1", "localhost", "::1"}:
            return build_opener(ProxyHandler({}))
        return build_opener()

    def complete(self, request: ModelTurnRequest) -> ModelTurnResponse:
        url = self._endpoint_url()
        payload = self._build_payload(request)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        api_key = os.environ.get(self.config.api_key_env, "") if self.config.api_key_env else ""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key or 'EMPTY'}",
        }
        opener = self._opener(url)

        last_error: Exception | None = None
        for attempt in range(self.config.max_transport_retries + 1):
            if self.budget is not None:
                self.budget.reserve_attempt(self.bound_nano_usd)
            started = time.perf_counter()
            req = Request(url, data=body, headers=headers, method="POST")
            try:
                with opener.open(req, timeout=self.config.timeout_seconds) as resp:
                    raw_text = resp.read().decode("utf-8")
                    http_status = getattr(resp, "status", 200)
                latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
                data = json.loads(raw_text)
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError("OpenAI-compatible response contained no choices")
                choice = choices[0]
                message = choice.get("message") or {}
                finish_reason = str(choice.get("finish_reason") or "stop")
                tool_calls = _extract_tool_calls(message)
                text_output = message.get("content")
                if text_output is None:
                    text_output = ""
                reasoning_content = message.get("reasoning_content") or message.get("reasoning")
                response = ModelTurnResponse(
                    request_sha256=request.fingerprint(),
                    provider_model_resolved=data.get("model"),
                    tool_calls=tool_calls,
                    text_output=str(text_output),
                    finish_reason=finish_reason,
                    truncated=(finish_reason == "length"),
                    usage=_extract_usage(data.get("usage")),
                )
                self.last_telemetry = {
                    "http_status": http_status,
                    "latency_ms": latency_ms,
                    "transport_attempts": attempt + 1,
                    "reasoning_content": reasoning_content,
                    "response_id": data.get("id"),
                }
                return response
            except HTTPError as exc:
                latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                self.last_telemetry = {
                    "http_status": exc.code,
                    "latency_ms": latency_ms,
                    "transport_attempts": attempt + 1,
                    "error": f"HTTPError {exc.code}: {err_body}",
                }
                last_error = RuntimeError(f"HTTPError {exc.code} from {url}: {err_body}")
                if exc.code < 500 or attempt >= self.config.max_transport_retries:
                    raise last_error from exc
            except (URLError, TimeoutError, OSError) as exc:
                latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
                self.last_telemetry = {
                    "http_status": None,
                    "latency_ms": latency_ms,
                    "transport_attempts": attempt + 1,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                last_error = exc
                if attempt >= self.config.max_transport_retries:
                    raise
            time.sleep(self.config.retry_backoff_seconds * (attempt + 1))

        assert last_error is not None
        raise last_error


class RecordingAdapter:
    """Wrap any ModelAdapter to record RecordedReplayAdapter-compatible JSONL tapes."""

    def __init__(
        self,
        inner: ModelAdapter,
        tape_path: Path,
        *,
        ledger_path: Path | None = None,
    ):
        self.inner = inner
        self.tape_path = Path(tape_path)
        self.ledger_path = Path(ledger_path) if ledger_path is not None else None
        self.tape_path.parent.mkdir(parents=True, exist_ok=True)
        if self.ledger_path is not None:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.recorded_count = 0

    def complete(self, request: ModelTurnRequest) -> ModelTurnResponse:
        started = time.perf_counter()
        response = self.inner.complete(request)
        wall_ms = round((time.perf_counter() - started) * 1000.0, 3)
        with self.tape_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(response), ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
        self.recorded_count += 1
        if self.ledger_path is not None:
            telemetry = getattr(self.inner, "last_telemetry", {})
            entry = {
                "seq": self.recorded_count,
                "request_id": request.request_id,
                "request_sha256": request.fingerprint(),
                "provider": request.provider,
                "model": request.model,
                "provider_model_resolved": response.provider_model_resolved,
                "config_sha256": request.config_sha256,
                "finish_reason": response.finish_reason,
                "truncated": response.truncated,
                "tool_call_names": [call.name for call in response.tool_calls],
                "usage": response.usage,
                "wall_ms": wall_ms,
                "telemetry": telemetry,
            }
            with self.ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
        return response

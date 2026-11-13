"""Metered DeepSeek JSON calls with private credentials and auditable usage."""

import json
import math
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import os

# USD per million tokens, peak rates checked against official docs 2026-11-12.
PEAK_RATES = {"cache_hit": 0.006, "cache_miss": 0.30, "output": 1.20}


class ModelBudgetExhausted(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(self, output, metrics, max_usd=0.50, max_tokens=1200, thinking="disabled"):
        if not math.isfinite(max_usd) or max_usd <= 0:
            raise ValueError("Spending cap must be finite and positive")
        if thinking not in {"disabled", "low"}:
            raise ValueError("Supported thinking settings are disabled and low")
        config = {"DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"],
                  "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
                  "DEEPSEEK_MODEL": "deepseek-flash"}
        self._key = config["DEEPSEEK_API_KEY"]
        self.base_url = config.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        if self.base_url != "https://api.deepseek.com":
            raise ValueError("This experiment uses the official DeepSeek endpoint")
        self.model = config.get("DEEPSEEK_MODEL", "deepseek-flash")
        if self.model != "deepseek-flash":
            raise ValueError("Pricing is configured for deepseek-flash; update rates before changing model")
        self.output = Path(output)
        self.metrics = metrics
        self.max_usd = max_usd
        self.max_tokens = max_tokens
        self.thinking = thinking
        self._committed = 0.0
        self._reserved = 0.0
        self._lock = threading.Lock()
        self.metrics.update(external_model_calls=0, external_model_cost=0.0,
                            external_model_cost_currency="USD",
                            external_model_cost_kind="estimated_peak_upper_bound",
                            usage_unknown_reserved_usd=0.0)
        self.audit = self.output / "model_calls.jsonl"

    def _log(self, record):
        content = json.dumps(record, ensure_ascii=False).replace(self._key, "[redacted]")
        with self._lock, self.audit.open("a", encoding="utf-8") as stream:
            stream.write(content + "\n")

    def complete(self, system, payload, call_id):
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        return self.complete_messages(messages, call_id)

    def complete_messages(self, messages, call_id, return_raw=False, tools=None):
        """Preserve an upstream client's guarded messages and JSON repair conversation."""
        body = {"model": self.model, "messages": messages,
                "thinking": {"type": "disabled" if self.thinking == "disabled" else "enabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": self.max_tokens, "stream": False}
        if tools is not None:
            body["tools"] = tools
            del body["response_format"]
        if self.thinking == "low":
            body["reasoning_effort"] = "low"
        else:
            body["temperature"] = 0
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        reserve = ((len(encoded) + 1024) * PEAK_RATES["cache_miss"]
                   + self.max_tokens * PEAK_RATES["output"]) / 1_000_000
        with self._lock:
            if self._committed + self._reserved + reserve > self.max_usd:
                raise ModelBudgetExhausted("Configured model-call spending cap reached")
            self._reserved += reserve
            self.metrics["external_model_calls"] += 1
        started = time.perf_counter()
        record = {"call_id": call_id, "request": body, "reserve_usd": reserve}
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=encoded, method="POST",
            headers={"Authorization": "Bearer " + self._key, "Content-Type": "application/json"},
        )
        estimate = reserve
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = json.loads(response.read())
            usage = raw["usage"]
            prompt = usage["prompt_tokens"]
            hit = usage.get("prompt_cache_hit_tokens", 0)
            miss = usage.get("prompt_cache_miss_tokens", prompt - hit)
            estimate = (hit * PEAK_RATES["cache_hit"] + miss * PEAK_RATES["cache_miss"]
                        + usage["completion_tokens"] * PEAK_RATES["output"]) / 1_000_000
            record.update(status="received", response=raw, estimated_peak_usd=estimate)
            allowed_finish = {"stop", "tool_calls"} if tools is not None else {"stop"}
            if raw["choices"][0]["finish_reason"] not in allowed_finish:
                raise ValueError("Response did not finish normally")
            if return_raw:
                return raw
            parsed = json.loads(raw["choices"][0]["message"]["content"])
            if not isinstance(parsed, dict):
                raise ValueError("Expected a JSON object")
            return parsed
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").replace(self._key, "[redacted]")
            record.update(status="http_error", http_status=error.code, detail=detail[:1200])
            # Reserve uncertainty conservatively, including rejected calls.
            raise RuntimeError(f"DeepSeek HTTP {error.code}; see sanitized call log") from None
        except Exception as error:
            record.update(status="error", error_type=type(error).__name__,
                          error_message=str(error).replace(self._key, "[redacted]")[:400])
            raise
        finally:
            record["latency_ms"] = (time.perf_counter() - started) * 1000
            with self._lock:
                self._reserved -= reserve
                self._committed += estimate
                self.metrics["external_model_cost"] = self._committed
                if "response" not in record:
                    self.metrics["usage_unknown_reserved_usd"] += reserve
            self._log(record)


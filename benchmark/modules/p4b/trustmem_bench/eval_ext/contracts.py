"""Vendor-neutral inputs and outputs for a metered benchmark turn."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Protocol


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    json_schema: JsonObject


@dataclass(frozen=True)
class ModelTurnRequest:
    request_id: str
    provider: str
    model: str
    system_prompt: str
    messages: tuple[JsonObject, ...]
    tools: tuple[ToolSpec, ...]
    tool_choice: str
    max_output_tokens: int
    config_sha256: str

    def fingerprint(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False)
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments_raw: str


@dataclass(frozen=True)
class ModelTurnResponse:
    request_sha256: str
    provider_model_resolved: str | None
    tool_calls: tuple[ToolCall, ...]
    text_output: str
    finish_reason: str
    truncated: bool
    usage: dict[str, int | None]


class ModelAdapter(Protocol):
    def complete(self, request: ModelTurnRequest) -> ModelTurnResponse: ...


class MemoryPolicyPlugin(Protocol):
    def on_session_open(self, session_id: str, pending_targets: list[JsonObject]) -> JsonObject: ...
    def on_tool_result(self, name: str, arguments: JsonObject, result: JsonObject) -> None: ...
    def lookup_archive(self, query: str) -> JsonObject: ...
    def on_session_close(self, session_id: str) -> JsonObject: ...


class AuditHook(Protocol):
    """Preserve the authoritative environment's snapshots, event logs and target outcomes."""

    def restore(self, world_snapshot: JsonObject, memory_snapshot: JsonObject) -> None: ...
    def observe_event(self, event: JsonObject) -> None: ...
    def terminal_record(self) -> JsonObject: ...


@dataclass(frozen=True)
class ParsedTurn:
    call: ToolCall | None = None
    arguments: JsonObject | None = None
    error: str | None = None


class ActionSurface(Protocol):
    def parse(self, request: ModelTurnRequest, response: ModelTurnResponse) -> ParsedTurn: ...


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    values = dict(pairs)
    if len(values) != len(pairs):
        raise ValueError("Duplicate JSON object key")
    return values


def reject_nonfinite(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


class NativeToolSurface:
    """Decode at most one action. The native environment validates fields and executes it."""

    def parse(self, request: ModelTurnRequest, response: ModelTurnResponse) -> ParsedTurn:
        if request.fingerprint() != response.request_sha256:
            raise ValueError("Response belongs to a different request")
        if response.truncated or response.finish_reason == "length":
            return ParsedTurn(error="truncated_turn")
        if response.finish_reason in {"error", "content_filter"}:
            return ParsedTurn(error=response.finish_reason)
        if not response.tool_calls:
            return ParsedTurn(error="missing_tool_call")
        if len(response.tool_calls) != 1:
            return ParsedTurn(error="multiple_tool_calls")
        call, = response.tool_calls
        if request.tool_choice == "none" or call.name not in {tool.name for tool in request.tools}:
            return ParsedTurn(call=call, error="tool_not_offered")
        try:
            args = json.loads(call.arguments_raw, object_pairs_hook=reject_duplicate_keys,
                              parse_constant=reject_nonfinite)
        except (ValueError, RecursionError):
            return ParsedTurn(call=call, error="invalid_tool_arguments_json")
        if not isinstance(args, dict):
            return ParsedTurn(call=call, error="tool_arguments_not_object")
        return ParsedTurn(call=call, arguments=args)

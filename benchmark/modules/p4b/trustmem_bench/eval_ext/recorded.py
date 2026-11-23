"""Read normalized responses in frozen request order, with no network transport."""

import json
from pathlib import Path

from .contracts import ModelTurnRequest, ModelTurnResponse, ToolCall


class RecordedReplayAdapter:
    def __init__(self, path: Path):
        with path.open(encoding="utf-8") as stream:
            self._rows = [json.loads(line) for line in stream]
        self._next = 0

    def complete(self, request: ModelTurnRequest) -> ModelTurnResponse:
        if self._next == len(self._rows):
            raise ValueError("No recorded response remains")
        row = self._rows[self._next]
        if row["request_sha256"] != request.fingerprint():
            raise ValueError(f"Recorded request does not match at row {self._next + 1}")
        output = ModelTurnResponse(
            request_sha256=row["request_sha256"],
            provider_model_resolved=row["provider_model_resolved"],
            tool_calls=tuple(ToolCall(**call) for call in row["tool_calls"]),
            text_output=row["text_output"],
            finish_reason=row["finish_reason"],
            truncated=row["truncated"],
            usage=row["usage"],
        )
        self._next += 1
        return output

    def assert_exhausted(self) -> None:
        if self._next != len(self._rows):
            raise ValueError("Unconsumed recorded responses")

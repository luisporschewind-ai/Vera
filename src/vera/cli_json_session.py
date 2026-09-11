"""NDJSON session driver over SessionController."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from vera.bootstrap import RuntimeDependencies
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame
from vera.redaction import Redactor
from vera.session.actions import CloseSession
from vera.session.controller import SessionController
from vera.session.protocol import (
    SessionActionCodec,
    SessionRecordCodec,
    input_failed_event,
)


class JsonSessionDriver:
    def __init__(
        self,
        dependencies: RuntimeDependencies,
        workspace: Path,
        model_profile: str,
        *,
        controller: SessionController | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self.controller = controller or SessionController(dependencies, workspace, model_profile)
        self.redactor = redactor or Redactor([])

    def run(self, input_stream: TextIO, output_stream: TextIO) -> int:
        exit_code = 0
        for raw in input_stream:
            line = raw.strip()
            if not line:
                continue
            try:
                action = SessionActionCodec.decode(line)
            except Exception as exc:
                message = str(self.redactor.redact(str(exc)))
                self._write_event(output_stream, input_failed_event(message))
                continue
            try:
                for output in self.controller.dispatch(action):
                    self._write_output(output_stream, output)
            except Exception as exc:
                message = str(self.redactor.redact(str(exc)))
                self._write_event(
                    output_stream,
                    input_failed_event(message, reason_code="dispatch_failed"),
                )
            if self.controller.exit_requested or self.controller.snapshot().closed:
                break
        if not self.controller.snapshot().closed:
            for output in self.controller.dispatch(CloseSession()):
                self._write_output(output_stream, output)
        return exit_code

    def _write_output(self, output_stream: TextIO, output: EventEnvelope | StreamFrame) -> None:
        record = SessionRecordCodec.from_output(output)
        output_stream.write(SessionRecordCodec.encode(record) + "\n")
        output_stream.flush()

    def _write_event(self, output_stream: TextIO, event: EventEnvelope) -> None:
        self._write_output(output_stream, event)

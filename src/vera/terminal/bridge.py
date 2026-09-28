"""Bridge SessionController workers to the Textual UI thread."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from textual.message import Message
from textual.worker import Worker, WorkerState

from vera.contracts.streaming import RuntimeOutput
from vera.redaction import Redactor
from vera.session.actions import SessionAction

if TYPE_CHECKING:
    from vera.session.controller import SessionController
    from vera.terminal.app import VeraTerminalApp


class RuntimeOutputReceived(Message):
    def __init__(self, output: RuntimeOutput, *, request_id: str | None = None) -> None:
        super().__init__()
        self.output = output
        self.request_id = request_id


class WorkerStopped(Message):
    def __init__(
        self,
        run_id: str | None,
        reason_code: str,
        *,
        action: SessionAction | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__()
        self.run_id = run_id
        self.reason_code = reason_code
        self.action = action
        self.request_id = request_id


class TerminalBridge:
    """Run controller.dispatch in a thread worker; post immutable messages only."""

    def __init__(
        self,
        app: VeraTerminalApp,
        controller: SessionController,
        *,
        redactor: Redactor | None = None,
    ) -> None:
        self.app = app
        self.controller = controller
        self.redactor = redactor or Redactor([])
        self._workers: list[Worker[None]] = []

    def submit(self, action: SessionAction) -> str:
        request_id = uuid4().hex
        worker = self.app.run_worker(
            lambda: self._dispatch(action, request_id),
            thread=True,
            exclusive=False,
            exit_on_error=False,
        )
        self._workers.append(worker)
        return request_id

    def cancel_workers(self) -> None:
        for worker in list(self._workers):
            if worker.state in {WorkerState.PENDING, WorkerState.RUNNING}:
                worker.cancel()
        self._workers.clear()

    def _dispatch(self, action: SessionAction, request_id: str) -> None:
        try:
            for output in self.controller.dispatch(action):
                self.app.post_message(
                    RuntimeOutputReceived(
                        self.redactor.redact_output(output), request_id=request_id
                    )
                )
            self.app.post_message(
                WorkerStopped(
                    self.controller.active_run_id,
                    "completed",
                    action=action,
                    request_id=request_id,
                )
            )
        except Exception as exc:
            message = str(self.redactor.redact(str(exc)))
            self.app.post_message(
                WorkerStopped(
                    self.controller.active_run_id,
                    f"worker_failed:{message}",
                    action=action,
                    request_id=request_id,
                )
            )

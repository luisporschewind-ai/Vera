"""Persistent interactive terminal session over the Vera Core contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from vera.bootstrap import RuntimeBuilder, RuntimeDependencies
from vera.cli_driver import ApprovalDecision
from vera.cli_presenter import HumanPresenter
from vera.cli_session_presenter import SessionPresenter
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame
from vera.session.actions import (
    CloseSession,
    ExecuteSlashCommand,
    ResolveSessionApproval,
    SubmitPrompt,
)
from vera.session.controller import SessionController
from vera.session.conversation import ConversationContext
from vera.session.models import ConversationStats, PermissionStatus, SessionStatus
from vera.session.status import SessionStatusService


class SessionIO(Protocol):
    def read(self, prompt: str) -> str: ...

    def write(self, text: str) -> None: ...

    def clear(self) -> None: ...


class InteractiveSession:
    """Plain-mode driver: SessionController plus human terminal I/O."""

    def __init__(
        self,
        dependencies: RuntimeDependencies,
        workspace: Path,
        model_profile: str,
        io: SessionIO,
        *,
        conversation: ConversationContext | None = None,
        status_service: SessionStatusService | None = None,
        runtime_builder: RuntimeBuilder | None = None,
        controller: SessionController | None = None,
    ) -> None:
        self.io = io
        self.presenter = HumanPresenter(io.write)
        self.session_presenter = SessionPresenter(io.write)
        self.controller = controller or SessionController(
            dependencies,
            workspace,
            model_profile,
            conversation=conversation,
            status_service=status_service,
            runtime_builder=runtime_builder,
        )
        self._exit_after_run = False

    @property
    def dependencies(self) -> RuntimeDependencies:
        return self.controller.dependencies

    @dependencies.setter
    def dependencies(self, value: RuntimeDependencies) -> None:
        from vera.persistence.run_store import RunStore

        self.controller.dependencies = value
        self.controller.store = RunStore(value.config.state_dir)

    @property
    def workspace(self) -> Path:
        return self.controller.workspace

    @property
    def model_profile(self) -> str:
        return self.controller.model_profile

    @model_profile.setter
    def model_profile(self, value: str) -> None:
        self.controller.model_profile = value

    @property
    def conversation(self) -> ConversationContext:
        return self.controller.conversation

    def run(self) -> int:
        for event in self.controller.bootstrap_events():
            self._present_session_event(event)
        while not self.controller.exit_requested:
            try:
                value = self.io.read("Vera > ").strip()
            except EOFError:
                return 0
            except KeyboardInterrupt:
                self.io.write("当前输入已清空。输入 /exit 可退出。")
                continue
            if not value:
                continue
            if value.startswith("/"):
                self._consume(self.controller.dispatch(ExecuteSlashCommand(raw=value)))
            else:
                self._consume(self.controller.dispatch(SubmitPrompt(text=value)))
                warning = self.controller.context_warning_event()
                if warning is not None:
                    self._present_session_event(warning)
            if self._exit_after_run or self.controller.exit_requested:
                return 0
        return 0

    def _consume(self, outputs: object) -> None:
        from collections.abc import Iterable

        assert isinstance(outputs, Iterable)
        pending_events: list[EventEnvelope] = []
        for item in outputs:
            if isinstance(item, StreamFrame):
                continue
            if not isinstance(item, EventEnvelope):
                continue
            if item.type.startswith("session."):
                if pending_events:
                    self.presenter.write_events(tuple(pending_events))
                    pending_events = []
                self._present_session_event(item)
                continue
            pending_events.append(item)
            if item.type == "approval.required":
                self.presenter.write_events(tuple(pending_events))
                pending_events = []
                decision = self._decide(item)
                if decision == "cancel" and self._exit_after_run:
                    self._consume(
                        self.controller.dispatch(
                            ResolveSessionApproval(
                                approval_id=str(item.payload["approval_id"]),
                                decision="cancel",
                            )
                        )
                    )
                    return
                self._consume(
                    self.controller.dispatch(
                        ResolveSessionApproval(
                            approval_id=str(item.payload["approval_id"]),
                            decision=decision,
                        )
                    )
                )
                return
        if pending_events:
            self.presenter.write_events(tuple(pending_events))

    def _present_session_event(self, event: EventEnvelope) -> None:
        if event.type == "session.status":
            status = SessionStatus.model_validate(event.payload)
            self.session_presenter.write_status(status)
            return
        if event.type == "session.context":
            self.session_presenter.write_context(ConversationStats.model_validate(event.payload))
            return
        if event.type == "session.permissions":
            self.session_presenter.write_permissions(
                PermissionStatus.model_validate(event.payload)
            )
            return
        if event.type == "session.help":
            self.io.write(str(event.payload.get("text", "")))
            return
        if event.type == "session.message":
            text = str(event.payload.get("text", ""))
            if event.payload.get("clear_display"):
                try:
                    self.io.clear()
                except Exception:
                    pass
            if text:
                self.io.write(text)
            return
        if event.type == "session.closed":
            return
        if event.type == "session.action_rejected":
            message = event.payload.get("message")
            self.io.write(str(message) if message else "操作被拒绝。")
            return
        text = event.payload.get("text")
        if isinstance(text, str) and text:
            self.io.write(text)

    def _decide(self, request: EventEnvelope) -> ApprovalDecision:
        prompt = self.presenter.approval_prompt(request)
        while True:
            try:
                value = self.io.read(f"{prompt}\nVera approval > ").strip().lower()
            except KeyboardInterrupt:
                self.io.write("当前任务已取消。")
                return "cancel"
            except EOFError:
                self._exit_after_run = True
                return "cancel"
            if value in {"approve", "reject", "cancel"}:
                return value  # type: ignore[return-value]
            self.io.write("无效审批输入；请输入 approve、reject 或 cancel。")

    def close(self) -> None:
        self._consume(self.controller.dispatch(CloseSession()))

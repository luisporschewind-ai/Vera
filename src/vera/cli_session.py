"""Persistent interactive terminal session over the Vera Core contracts."""

from contextlib import suppress
from pathlib import Path
from typing import Protocol

from vera.bootstrap import RuntimeBuilder, RuntimeDependencies
from vera.cli_driver import ApprovalDecision
from vera.cli_presenter import HumanPresenter
from vera.cli_session_presenter import SessionPresenter
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame
from vera.presentation.diagnostics_copy import format_config_body, format_doctor_body
from vera.session.actions import (
    CloseSession,
    ExecuteSlashCommand,
    QueuePrompt,
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
            elif (
                self.controller.pending_approval_id is not None
                or self.controller.active_run_id is not None
            ):
                self._consume(self.controller.dispatch(QueuePrompt(text=value)))
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
            self.session_presenter.write_permissions(PermissionStatus.model_validate(event.payload))
            return
        if event.type in {
            "session.help",
            "session.diff",
            "session.review",
            "session.doctor",
            "session.config",
            "session.usage",
            "session.shortcuts",
            "session.theme",
            "session.listed",
            "session.loaded",
        }:
            text = event.payload.get("text")
            if isinstance(text, str) and text:
                self.io.write(text)
                return
            self.io.write(_structured_plain(event.type, event.payload))
            return
        if event.type == "session.user_prompt":
            prompt = str(event.payload.get("text", "")).strip()
            if prompt:
                self.io.write(f"你：{prompt}")
            return
        if event.type == "session.message":
            message_text = str(event.payload.get("text", ""))
            if event.payload.get("clear_display"):
                with suppress(Exception):
                    self.io.clear()
            if message_text:
                self.io.write(message_text)
            return
        if event.type == "session.closed":
            return
        if event.type == "session.prompt_queued":
            self.io.write("已排队下一条输入。下一次运行结束后提交。")
            return
        if event.type == "session.prompt_queue_cleared":
            self.io.write("已撤销排队输入。")
            return
        if event.type == "session.prompt_queue_flushed":
            self.io.write("正在提交排队输入。")
            return
        if event.type == "session.editor_preview":
            argv = event.payload.get("argv", [])
            rendered = " ".join(str(part) for part in argv) if isinstance(argv, list) else ""
            self.io.write(f"外部编辑器命令：{rendered}")
            return
        if event.type == "session.action_rejected":
            rejected = event.payload.get("message")
            self.io.write(str(rejected) if isinstance(rejected, str) else "操作被拒绝。")
            return
        if event.type in {"session.persistence_changed", "session.close_warning"}:
            advice = event.payload.get("advice")
            if isinstance(advice, str) and advice.strip():
                self.io.write(advice.strip())
            return
        fallback = event.payload.get("text")
        if isinstance(fallback, str) and fallback:
            self.io.write(fallback)

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


def _structured_plain(event_type: str, payload: dict[str, object]) -> str:
    if event_type == "session.usage":
        return (
            f"calls {payload.get('calls')}\t"
            f"input {payload.get('input_tokens')}\t"
            f"output {payload.get('output_tokens')}\t"
            f"total {payload.get('total_tokens')}"
        )
    if event_type == "session.theme":
        return f"theme {payload.get('theme')}"
    if event_type == "session.review":
        files = payload.get("files") or []
        return f"review files={len(files) if isinstance(files, list) else 0}"
    if event_type == "session.doctor":
        return format_doctor_body(payload)
    if event_type == "session.config":
        return format_config_body(payload)
    if event_type == "session.loaded":
        session_id = payload.get("session_id", "")
        title = payload.get("title", "")
        return f"已恢复会话 {session_id} {title}".strip()
    if event_type == "session.listed":
        return str(payload.get("text") or "当前工作区没有会话。")
    return event_type

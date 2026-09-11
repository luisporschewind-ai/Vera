"""Persistent interactive terminal session over the Vera Core contracts."""

from __future__ import annotations

import shlex
from contextlib import suppress
from pathlib import Path
from typing import Protocol

from vera.bootstrap import RuntimeDependencies
from vera.cli_driver import ApprovalDecision, drive_run
from vera.cli_presenter import HumanPresenter
from vera.cli_session_presenter import SessionPresenter
from vera.contracts.commands import RollbackRun, StartRun
from vera.contracts.events import EventEnvelope
from vera.persistence.run_store import RunStore
from vera.session.conversation import ConversationContext
from vera.session.permissions import permission_status
from vera.session.status import SessionStatusService


class SessionIO(Protocol):
    def read(self, prompt: str) -> str: ...

    def write(self, text: str) -> None: ...

    def clear(self) -> None: ...


class InteractiveSession:
    """Run independent goals through one Runtime while the terminal stays open."""

    def __init__(
        self,
        dependencies: RuntimeDependencies,
        workspace: Path,
        model_profile: str,
        io: SessionIO,
        *,
        conversation: ConversationContext | None = None,
        status_service: SessionStatusService | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.workspace = workspace.resolve()
        self.model_profile = model_profile
        self.io = io
        self.presenter = HumanPresenter(io.write)
        self.session_presenter = SessionPresenter(io.write)
        self.store = RunStore(dependencies.config.state_dir)
        self.conversation = conversation or ConversationContext(
            dependencies.config.limits.max_conversation_bytes
        )
        self.status_service = status_service or SessionStatusService()
        self._exit_after_run = False

    def run(self) -> int:
        self._write_status()
        self.io.write("输入 /help 查看命令")
        while True:
            try:
                value = self.io.read("Vera > ").strip()
            except EOFError:
                return 0
            except KeyboardInterrupt:
                self.io.write("当前输入已清空。输入 /exit 可退出。")
                continue
            if not value:
                continue
            if value in {"/exit", "/quit"}:
                return 0
            if value.startswith("/"):
                self._handle_command(value)
                continue
            self._run_goal(value)
            if self._exit_after_run:
                return 0

    def _model_name(self) -> str:
        provider = self.dependencies.config.providers.get(self.model_profile)
        if provider is None:
            return "unavailable"
        return provider.model

    def _write_status(self) -> None:
        status = self.status_service.snapshot(
            workspace=self.workspace,
            model_profile=self.model_profile,
            model_name=self._model_name(),
            conversation=self.conversation.stats(),
            permissions=permission_status(self.dependencies.runtime.command_policy),
        )
        self.session_presenter.write_status(status)

    def _run_goal(self, goal: str) -> None:
        if not self.conversation.can_accept(goal):
            self.io.write("当前上下文已满。请先执行 /compact 或 /new。")
            return
        events = drive_run(
            self.dependencies.runtime,
            StartRun(
                goal=goal,
                workspace_root=self.workspace,
                model_profile=self.model_profile,
                conversation=self.conversation.snapshot(),
            ),
            self._decide,
            self.presenter.write_events,
        )
        self.conversation.record_run(goal, events)
        if self.conversation.stats().warning:
            self.io.write("上下文已接近上限。可使用 /compact 或 /new。")

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

    def _handle_command(self, raw: str) -> None:
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.io.write(f"命令格式错误：{exc}")
            return
        command = parts[0]
        args = parts[1:]
        if command == "/help" and not args:
            self._write_help()
        elif command == "/status" and not args:
            self._write_status()
        elif command == "/context" and not args:
            self.session_presenter.write_context(self.conversation.stats())
        elif command == "/permissions" and not args:
            self.session_presenter.write_permissions(
                permission_status(self.dependencies.runtime.command_policy)
            )
        elif command == "/new" and not args:
            session_id = self.conversation.reset()
            self.io.write(f"已开始新会话：{session_id}")
        elif command == "/clear" and not args:
            session_id = self.conversation.reset()
            with suppress(Exception):
                self.io.clear()
            self.io.write(f"已清空显示并开始新会话：{session_id}")
        elif command == "/runs" and not args:
            self._write_runs()
        elif command == "/show" and len(args) == 1:
            self._show(args[0])
        elif command == "/rollback" and len(args) == 1:
            self._rollback(args[0])
        elif command in {"/show", "/rollback"}:
            self.io.write(f"用法：{command} <run-id>")
        elif command in {
            "/help",
            "/status",
            "/context",
            "/permissions",
            "/new",
            "/clear",
            "/runs",
            "/exit",
            "/quit",
        }:
            self.io.write(f"用法：{command}")
        else:
            self.io.write(f"未知命令：{command}。输入 /help 查看可用命令。")

    def _write_help(self) -> None:
        self.io.write(
            "会话命令：\n"
            "  /help                 显示帮助\n"
            "  /status               显示会话状态\n"
            "  /context              显示上下文统计\n"
            "  /permissions          显示有效权限边界\n"
            "  /new                  清空上下文并开始新会话\n"
            "  /clear                清空显示与上下文\n"
            "  /compact [focus]      压缩当前上下文\n"
            "  /model [profile]      查看或切换模型\n"
            "  /runs                 列出任务\n"
            "  /show <run-id>         显示任务事件\n"
            "  /rollback <run-id>     安全回滚任务修改\n"
            "  /exit 或 /quit         退出\n"
            "审批输入：approve、reject 或 cancel"
        )

    def _write_runs(self) -> None:
        summaries = self.store.list_runs()
        if not summaries:
            self.io.write("暂无 run。")
            return
        for summary in summaries:
            self.io.write(
                f"{summary.run_id}\t{summary.goal_summary}\t{summary.terminal_state or 'active'}"
            )

    def _show(self, run_id: str) -> None:
        events = self.store.read_events(run_id)
        if not events:
            self.io.write(f"未找到 run：{run_id}")
            return
        self.presenter.write_events(events)

    def _rollback(self, run_id: str) -> None:
        events = tuple(self.dependencies.runtime.handle(RollbackRun(run_id=run_id)))
        if not events:
            self.io.write(f"未找到可回滚的 Checkpoint：{run_id}")
            return
        self.presenter.write_events(events)

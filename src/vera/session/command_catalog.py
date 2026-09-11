"""Shared slash-command catalog for TUI completions and help."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from vera.session.controller import SessionSnapshot


@dataclass(frozen=True, slots=True)
class CommandDescriptor:
    name: str
    usage: str
    description: str
    enabled_when: Callable[[SessionSnapshot], bool] = lambda _snapshot: True


class CommandCatalog:
    def __init__(self, commands: tuple[CommandDescriptor, ...] | None = None) -> None:
        self._commands = commands or DEFAULT_COMMANDS

    def list(self, prefix: str, snapshot: SessionSnapshot) -> tuple[CommandDescriptor, ...]:
        needle = prefix if prefix.startswith("/") else f"/{prefix}"
        return tuple(
            item
            for item in self._commands
            if item.name.startswith(needle) and item.enabled_when(snapshot)
        )


def _always(_snapshot: SessionSnapshot) -> bool:
    return True


DEFAULT_COMMANDS: tuple[CommandDescriptor, ...] = (
    CommandDescriptor("/help", "/help", "显示帮助", _always),
    CommandDescriptor("/status", "/status", "显示会话状态", _always),
    CommandDescriptor("/context", "/context", "显示上下文统计", _always),
    CommandDescriptor("/permissions", "/permissions", "显示有效权限边界", _always),
    CommandDescriptor("/new", "/new", "清空上下文并开始新会话", _always),
    CommandDescriptor("/clear", "/clear", "清空显示与上下文", _always),
    CommandDescriptor("/compact", "/compact [focus]", "压缩当前上下文", _always),
    CommandDescriptor("/model", "/model [profile]", "查看或切换模型", _always),
    CommandDescriptor("/runs", "/runs", "列出任务", _always),
    CommandDescriptor("/show", "/show <run-id>", "显示任务事件", _always),
    CommandDescriptor("/rollback", "/rollback <run-id>", "安全回滚任务修改", _always),
    CommandDescriptor("/recover", "/recover [run-id]", "查看待恢复任务", _always),
    CommandDescriptor("/resume", "/resume <run-id>", "继续可恢复任务", _always),
    CommandDescriptor("/abandon", "/abandon <run-id>", "放弃中断任务", _always),
    CommandDescriptor("/exit", "/exit", "退出", _always),
    CommandDescriptor("/quit", "/quit", "退出", _always),
)

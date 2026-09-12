"""Single slash-command registry for help, completion, and execution."""

from __future__ import annotations

import difflib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vera.session.controller import SessionSnapshot


@dataclass(frozen=True, slots=True)
class CommandDescriptor:
    name: str
    usage: str
    description: str
    group: str
    handler: str
    aliases: tuple[str, ...] = ()
    args: str = "none"
    enabled_when: Callable[[SessionSnapshot], bool] = lambda _snapshot: True


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str
    handler: str
    args: tuple[str, ...]
    unknown: bool = False
    suggestions: tuple[str, ...] = ()


class CommandCatalog:
    def __init__(self, commands: tuple[CommandDescriptor, ...] | None = None) -> None:
        self._commands = commands or DEFAULT_COMMANDS
        self._by_name = {item.name: item for item in self._commands}
        for item in self._commands:
            for alias in item.aliases:
                self._by_name.setdefault(alias, item)

    def all(self) -> tuple[CommandDescriptor, ...]:
        return self._commands

    def get(self, name: str) -> CommandDescriptor | None:
        key = name if name.startswith("/") else f"/{name}"
        return self._by_name.get(key)

    def list(self, prefix: str, snapshot: SessionSnapshot) -> tuple[CommandDescriptor, ...]:
        needle = prefix if prefix.startswith("/") else f"/{prefix}"
        return tuple(
            item
            for item in self._commands
            if (
                item.name.startswith(needle)
                or any(alias.startswith(needle) for alias in item.aliases)
            )
            and item.enabled_when(snapshot)
        )

    def suggest(self, name: str) -> tuple[str, ...]:
        names = [item.name for item in self._commands]
        return tuple(difflib.get_close_matches(name, names, n=3, cutoff=0.5))

    def parse(self, parts: Sequence[str]) -> ParsedCommand:
        if not parts:
            return ParsedCommand(name="", handler="", args=(), unknown=True)
        name = parts[0]
        args = tuple(parts[1:])
        command = self.get(name)
        if command is None:
            return ParsedCommand(
                name=name,
                handler="",
                args=args,
                unknown=True,
                suggestions=self.suggest(name),
            )
        return ParsedCommand(name=command.name, handler=command.handler, args=args)

    def help_text(self, snapshot: SessionSnapshot) -> str:
        groups: dict[str, list[CommandDescriptor]] = {}
        for item in self._commands:
            if not item.enabled_when(snapshot):
                continue
            groups.setdefault(item.group, []).append(item)
        lines = ["会话命令："]
        for group in ("开始", "会话", "代码与证据", "恢复", "安全", "外观"):
            items = groups.get(group)
            if not items:
                continue
            lines.append(f"  {group}")
            for item in items:
                lines.append(f"    {item.usage:<22} {item.description}")
        lines.append("审批输入：approve、reject 或 cancel")
        return "\n".join(lines)


def _always(_snapshot: SessionSnapshot) -> bool:
    return True


DEFAULT_COMMANDS: tuple[CommandDescriptor, ...] = (
    CommandDescriptor("/help", "/help", "显示帮助", "开始", "help", enabled_when=_always),
    CommandDescriptor("/status", "/status", "显示会话状态", "开始", "status"),
    CommandDescriptor("/context", "/context", "显示上下文统计", "会话", "context"),
    CommandDescriptor(
        "/permissions",
        "/permissions",
        "显示有效权限边界",
        "安全",
        "permissions",
    ),
    CommandDescriptor("/new", "/new", "清空上下文并开始新会话", "会话", "new"),
    CommandDescriptor("/clear", "/clear", "清空显示与上下文", "会话", "clear"),
    CommandDescriptor(
        "/compact",
        "/compact [focus]",
        "压缩当前上下文",
        "会话",
        "compact",
        args="optional",
    ),
    CommandDescriptor(
        "/model",
        "/model [profile]",
        "查看或切换模型",
        "会话",
        "model",
        args="optional",
    ),
    CommandDescriptor("/runs", "/runs", "列出任务", "代码与证据", "runs"),
    CommandDescriptor(
        "/show",
        "/show <run-id>",
        "显示任务事件",
        "代码与证据",
        "show",
        args="required",
    ),
    CommandDescriptor(
        "/diff",
        "/diff [run-id]",
        "展示权威 Diff",
        "代码与证据",
        "diff",
        args="optional",
    ),
    CommandDescriptor(
        "/review",
        "/review [run-id]",
        "只读投影风险摘要",
        "代码与证据",
        "review",
        args="optional",
    ),
    CommandDescriptor(
        "/rollback",
        "/rollback <run-id>",
        "安全回滚任务修改",
        "恢复",
        "rollback",
        args="required",
    ),
    CommandDescriptor(
        "/recover",
        "/recover [run-id]",
        "查看待恢复任务",
        "恢复",
        "recover",
        args="optional",
    ),
    CommandDescriptor(
        "/resume",
        "/resume <run-id>",
        "继续可恢复任务",
        "恢复",
        "resume",
        args="required",
    ),
    CommandDescriptor(
        "/abandon",
        "/abandon <run-id>",
        "放弃中断任务",
        "恢复",
        "abandon",
        args="required",
    ),
    CommandDescriptor("/doctor", "/doctor", "检查本地环境与配置", "安全", "doctor"),
    CommandDescriptor("/config", "/config", "只读显示有效配置", "安全", "config"),
    CommandDescriptor("/usage", "/usage", "显示当前会话用量", "会话", "usage"),
    CommandDescriptor("/shortcuts", "/shortcuts", "显示可用快捷键", "外观", "shortcuts"),
    CommandDescriptor(
        "/theme",
        "/theme [name]",
        "查看或切换会话主题",
        "外观",
        "theme",
        args="optional",
    ),
    CommandDescriptor("/exit", "/exit", "退出", "会话", "exit", aliases=("/quit",)),
    CommandDescriptor("/quit", "/quit", "退出", "会话", "exit"),
)

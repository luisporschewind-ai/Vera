"""Classify verification commands before they reach the host process table."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from vera.contracts.verification import VerificationCommand


class CommandDecisionKind(StrEnum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class CommandDecision:
    kind: CommandDecisionKind
    reason: str


class CommandPolicy:
    _safe_commands = {
        ("git", "status", "--short"),
        ("git", "diff", "--check"),
    }
    _shells = frozenset({"sh", "bash", "zsh", "fish", "dash", "cmd", "powershell", "pwsh"})
    _destructive = frozenset({"rm", "rmdir", "unlink", "del"})
    _privileged = frozenset({"sudo", "doas", "su"})

    def __init__(self, user_allowed_prefixes: tuple[tuple[str, ...], ...] = ()) -> None:
        self.user_allowed_prefixes = user_allowed_prefixes

    def classify(self, command: VerificationCommand) -> CommandDecision:
        argv = command.argv
        if not argv or any("\x00" in item for item in argv) or "\x00" in command.cwd:
            return CommandDecision(CommandDecisionKind.FORBIDDEN, "invalid command")
        executable = Path(argv[0]).name
        if (
            executable in self._shells
            or executable in self._destructive
            or executable in self._privileged
        ):
            return CommandDecision(
                CommandDecisionKind.FORBIDDEN, "shell, deletion, or privilege command"
            )
        if (
            executable == "git"
            and len(argv) >= 2
            and (
                argv[1] in {"clean", "checkout", "restore"}
                or (argv[1] == "reset" and "--hard" in argv[2:])
            )
        ):
            return CommandDecision(CommandDecisionKind.FORBIDDEN, "destructive git command")
        if argv in self._safe_commands:
            return CommandDecision(
                CommandDecisionKind.ALLOWED, "built-in safe verification command"
            )
        if any(argv[: len(prefix)] == prefix for prefix in self.user_allowed_prefixes):
            return CommandDecision(CommandDecisionKind.ALLOWED, "user-approved command prefix")
        return CommandDecision(
            CommandDecisionKind.APPROVAL_REQUIRED,
            "该进程以当前系统用户权限运行，Vera 第一版不提供 OS 沙箱",
        )

"""Pure policy rules evaluated in fixed precedence order."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.tool_actions import ToolEffect
from vera.policy.models import PolicyAction, PolicyActionKind, PolicyDecisionKind, RiskLevel
from vera.policy.snapshot import EffectivePolicySnapshot, EffectivePolicySnapshotV2

_SHELLS = frozenset({"sh", "bash", "zsh", "fish", "dash", "cmd", "powershell", "pwsh"})
_DESTRUCTIVE = frozenset({"rm", "rmdir", "unlink", "del"})
_PRIVILEGED = frozenset({"sudo", "doas", "su"})
_WRAPPERS = frozenset({"env", "xargs", "busybox", "nice", "nohup", "timeout", "stdbuf"})
_SAFE_COMMANDS = {
    ("git", "status", "--short"),
    ("git", "diff", "--check"),
}


def risk_level_for_effect(effect: ToolEffect, *, trusted: bool) -> RiskLevel:
    if effect is ToolEffect.SECRET_ACCESS:
        return RiskLevel.FORBIDDEN
    if effect in {ToolEffect.NETWORK_ACCESS, ToolEffect.EXTERNAL_SERVICE}:
        return RiskLevel.HIGH
    if effect is ToolEffect.PROCESS_EXECUTE:
        return RiskLevel.MODERATE
    if effect is ToolEffect.WORKSPACE_WRITE and not trusted:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def _match(kind: PolicyDecisionKind, reason_code: str, reason: str, rule: str) -> dict[str, str]:
    return {
        "decision": kind.value,
        "reason_code": reason_code,
        "reason": reason,
        "matched_rule": rule,
    }


def evaluate_rule(
    snapshot: EffectivePolicySnapshot | EffectivePolicySnapshotV2,
    action: PolicyAction,
) -> dict[str, str] | None:
    if action.kind is PolicyActionKind.COMMAND_EXECUTE:
        return _command_rule(snapshot, action)
    if action.kind in {PolicyActionKind.PATH_READ, PolicyActionKind.PATH_WRITE}:
        return _path_rule(snapshot, action)
    if action.kind is PolicyActionKind.TOOL_EXECUTE:
        tool = action.resource
        if tool in snapshot.project_denied_tools:
            return _match(
                PolicyDecisionKind.DENY,
                "project_tool_denied",
                "project configuration denies this tool",
                "project_denied_tools",
            )
        if tool in {"read_file", "list_directory", "search_text", "propose_changeset"}:
            return _match(
                PolicyDecisionKind.ALLOW,
                "builtin_tool_allowed",
                "built-in tool",
                "builtin_tools",
            )
        return _match(
            PolicyDecisionKind.DENY,
            "unknown_tool",
            "unknown tool",
            "unknown_tool",
        )
    if action.kind is PolicyActionKind.CHANGESET_APPLY:
        return _match(
            PolicyDecisionKind.APPROVAL_REQUIRED,
            "changeset_approval_required",
            "Change Set requires approval",
            "changeset_apply",
        )
    if action.kind in {
        PolicyActionKind.CHECKPOINT_RESTORE,
        PolicyActionKind.RECOVERY_RESUME,
        PolicyActionKind.STATE_MIGRATE,
    }:
        return _match(
            PolicyDecisionKind.APPROVAL_REQUIRED,
            "recovery_approval_required",
            "recovery action requires approval",
            action.kind.value,
        )
    return _match(
        PolicyDecisionKind.DENY,
        "unknown_action",
        "unknown action",
        "unknown_action",
    )


def _command_rule(
    snapshot: EffectivePolicySnapshot | EffectivePolicySnapshotV2,
    action: PolicyAction,
) -> dict[str, str] | None:
    argv = action.argv
    cwd = str(action.metadata.get("cwd", "."))
    if not argv or any("\x00" in item for item in argv) or "\x00" in cwd:
        return _match(PolicyDecisionKind.DENY, "invalid_command", "invalid command", "hard_forbid")
    if _cwd_forbidden(cwd):
        return _match(
            PolicyDecisionKind.DENY,
            "cwd_forbidden",
            "command cwd must stay inside the workspace",
            "hard_forbid",
        )
    names = tuple(_executable_name(item) for item in argv)
    executable = names[0]
    if executable in _PRIVILEGED:
        return _match(
            PolicyDecisionKind.DENY,
            "privilege_forbidden",
            "privilege escalation forbidden",
            "hard_forbid",
        )
    if executable in _SHELLS:
        return _match(
            PolicyDecisionKind.DENY, "shell_forbidden", "shell interpreter forbidden", "hard_forbid"
        )
    if executable in _DESTRUCTIVE:
        return _match(
            PolicyDecisionKind.DENY,
            "deletion_forbidden",
            "destructive deletion forbidden",
            "hard_forbid",
        )
    if executable in _WRAPPERS and any(
        name in _SHELLS | _PRIVILEGED | _DESTRUCTIVE for name in names[1:]
    ):
        return _match(
            PolicyDecisionKind.DENY,
            "nested_interpreter_forbidden",
            "nested shell or privileged interpreter forbidden",
            "hard_forbid",
        )
    if (
        executable == "git"
        and len(argv) >= 2
        and (
            argv[1] in {"clean", "checkout", "restore"}
            or (argv[1] == "reset" and "--hard" in argv[2:])
        )
    ):
        return _match(
            PolicyDecisionKind.DENY,
            "destructive_git_forbidden",
            "destructive git command",
            "hard_forbid",
        )
    if any(argv[: len(prefix)] == prefix for prefix in snapshot.user_allowed_command_prefixes):
        return _match(
            PolicyDecisionKind.ALLOW,
            "user_prefix_allowed",
            "user-approved command prefix",
            "user_prefix",
        )
    if argv in _SAFE_COMMANDS:
        return _match(
            PolicyDecisionKind.ALLOW,
            "builtin_safe_command",
            "built-in safe verification command",
            "builtin_safe",
        )
    return _match(
        PolicyDecisionKind.APPROVAL_REQUIRED,
        "command_not_preapproved",
        "该进程以当前系统用户权限运行，Vera 第一版不提供 OS 沙箱",
        "default_approval",
    )


def _executable_name(value: str) -> str:
    name = Path(value).name.lower()
    if name.endswith(".exe"):
        return name[:-4]
    return name


def _cwd_forbidden(cwd: str) -> bool:
    candidate = Path(cwd)
    if candidate.is_absolute():
        return True
    return any(part == ".." for part in candidate.parts)


def _path_rule(
    snapshot: EffectivePolicySnapshot | EffectivePolicySnapshotV2,
    action: PolicyAction,
) -> dict[str, str] | None:
    name = Path(action.resource).name
    for pattern in snapshot.protected_path_globs + snapshot.project_denied_path_globs:
        if Path(name).match(pattern) or Path(action.resource).match(pattern):
            return _match(
                PolicyDecisionKind.DENY,
                "sensitive_path_forbidden",
                "sensitive or project-denied path",
                "sensitive_paths",
            )
    return _match(
        PolicyDecisionKind.ALLOW,
        "path_allowed",
        "path allowed by policy",
        "workspace_paths",
    )

"""Pure policy rules evaluated in fixed precedence order."""

from __future__ import annotations

from pathlib import Path

from vera.policy.models import PolicyAction, PolicyActionKind, PolicyDecisionKind
from vera.policy.snapshot import EffectivePolicySnapshot

_SHELLS = frozenset({"sh", "bash", "zsh", "fish", "dash", "cmd", "powershell", "pwsh"})
_DESTRUCTIVE = frozenset({"rm", "rmdir", "unlink", "del"})
_PRIVILEGED = frozenset({"sudo", "doas", "su"})
_SAFE_COMMANDS = {
    ("git", "status", "--short"),
    ("git", "diff", "--check"),
}


def _match(kind: PolicyDecisionKind, reason_code: str, reason: str, rule: str) -> dict[str, str]:
    return {
        "decision": kind.value,
        "reason_code": reason_code,
        "reason": reason,
        "matched_rule": rule,
    }


def evaluate_rule(snapshot: EffectivePolicySnapshot, action: PolicyAction) -> dict[str, str] | None:
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


def _command_rule(snapshot: EffectivePolicySnapshot, action: PolicyAction) -> dict[str, str] | None:
    argv = action.argv
    cwd = str(action.metadata.get("cwd", "."))
    if not argv or any("\x00" in item for item in argv) or "\x00" in cwd:
        return _match(PolicyDecisionKind.DENY, "invalid_command", "invalid command", "hard_forbid")
    executable = Path(argv[0]).name
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


def _path_rule(snapshot: EffectivePolicySnapshot, action: PolicyAction) -> dict[str, str] | None:
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

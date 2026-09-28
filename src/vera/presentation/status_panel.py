"""Human copy for the startup /status panel. Shared by TUI and Plain."""

from __future__ import annotations

from vera.session.models import PermissionStatus, SessionStatus


def format_sandbox_status(status: PermissionStatus) -> str:
    if status.sandbox_state == "setup_required":
        return "未配置 · 项目命令禁用"
    if status.sandbox_state == "configured":
        return "已配置 · 项目命令必须使用 OS 沙盒，执行前检查"
    if status.sandbox_state == "required":
        return "项目命令要求沙盒 · 后端状态未确认"
    return "OS sandbox" if status.os_sandbox else "no OS sandbox"


def format_status_panel(status: SessionStatus) -> str:
    git = _git_line(status)
    sandbox = format_sandbox_status(status.permissions)
    session = status.context
    return "\n".join(
        (
            f"Vera {status.version}",
            "",
            f"Model       {status.model_profile} / {status.model_name}",
            f"Reasoning   {status.reasoning.display_label()}",
            f"Workspace   {status.workspace}",
            f"Git         {git}",
            f"Session     {session.session_id} · {session.message_count} messages"
            f" · {session.persistent_state}"
            + (f" · {session.source}" if session.source != "new" else "")
            + (f" · {session.title}" if session.title and session.title != "新会话" else ""),
            (
                "Context     "
                f"{session.context_bytes}/{session.max_bytes} bytes"
                f" · compacted {session.compaction_count}"
            ),
            f"Approval    {status.permissions.approval_mode}",
            f"Policy      {status.permissions.policy_mode} · "
            f"{'trusted' if status.permissions.trusted else 'untrusted'}",
            f"Execution   {status.permissions.execution_boundary} · {sandbox}",
        )
    )


def _git_line(status: SessionStatus) -> str:
    git = status.git
    if not git.available:
        return "not a repository"
    branch = git.branch or "unavailable"
    dirty = "unavailable" if git.dirty is None else "dirty" if git.dirty else "clean"
    return f"{branch} · {dirty}"

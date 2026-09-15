"""Human copy for the startup /status panel. Shared by TUI and Plain."""

from __future__ import annotations

from vera.session.models import SessionStatus


def format_status_panel(status: SessionStatus) -> str:
    git = _git_line(status)
    sandbox = "OS sandbox" if status.permissions.os_sandbox else "no OS sandbox"
    session = status.context
    return "\n".join(
        (
            f"Vera {status.version}",
            "",
            f"Model       {status.model_profile} / {status.model_name}",
            f"Workspace   {status.workspace}",
            f"Git         {git}",
            f"Session     {session.session_id} · {session.message_count} messages",
            (
                "Context     "
                f"{session.context_bytes}/{session.max_bytes} bytes"
                f" · compacted {session.compaction_count}"
            ),
            f"Approval    {status.permissions.approval_mode}",
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

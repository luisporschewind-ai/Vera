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
            f"Skill       {_skill_line(status)}",
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


def _skill_line(status: SessionStatus) -> str:
    pending = status.skill_selection
    pending_text = "none"
    if pending.status == "selected":
        pending_text = f"pending {pending.skill_id}"
    elif pending.status == "invalid":
        pending_text = f"invalid {pending.selector or '-'}"
    active = status.active_skill_snapshot
    active_text = f"active {active.skill_id}" if active is not None else "active none"
    return f"{pending_text} · {active_text}"

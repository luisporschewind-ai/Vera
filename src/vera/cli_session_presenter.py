"""Human-readable rendering for session status surfaces."""

from __future__ import annotations

from collections.abc import Callable

from vera.presentation.status_panel import format_status_panel
from vera.session.models import ConversationStats, PermissionStatus, SessionStatus


class SessionPresenter:
    def __init__(self, write: Callable[[str], None]) -> None:
        self._write = write

    def write_status(self, status: SessionStatus) -> None:
        for line in format_status_panel(status).splitlines():
            self._write(line)

    def write_context(self, stats: ConversationStats) -> None:
        ratio = (stats.context_bytes / stats.max_bytes) if stats.max_bytes else 0.0
        warning = " · warning" if stats.warning else ""
        self._write(
            f"Context  {stats.message_count} messages · "
            f"{stats.context_bytes}/{stats.max_bytes} bytes"
            f" ({ratio:.0%}){warning}"
        )
        self._write(f"Session  {stats.session_id}")
        self._write(f"State    {stats.persistent_state} · {stats.source}")
        if stats.last_error_code:
            self._write(f"Persist  {stats.last_error_code}")
        self._write(f"Compacted {stats.compaction_count}")

    def write_permissions(self, status: PermissionStatus) -> None:
        self._write(f"Approval mode     {status.approval_mode}")
        self._write(f"Change Set        {status.changeset_approval}")
        self._write(f"Command policy    {status.command_policy}")
        self._write(f"Policy version    {status.policy_version}")
        if status.policy_hash_prefix:
            self._write(f"Policy hash       {status.policy_hash_prefix}")
        if status.hard_denies:
            self._write(f"Hard denies       {', '.join(status.hard_denies)}")
        if status.user_allowed_prefixes:
            for prefix in status.user_allowed_prefixes:
                self._write(f"Allowed prefix    {' '.join(prefix)}")
        else:
            self._write("Allowed prefix    (none)")
        self._write(f"Execution         {status.execution_boundary}")
        sandbox = "OS sandbox" if status.os_sandbox else "no OS sandbox"
        self._write(f"Sandbox           {sandbox}")

"""Project RuntimeOutput into immutable timeline mutations."""

from __future__ import annotations

from datetime import datetime

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput, StreamFrame
from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.errors import SideEffectFact
from vera.presentation.event_projector import EventProjector
from vera.presentation.mutations import AppendBlock, FocusBlock, TimelineMutation, UpdateBlock
from vera.presentation.prompt_block import project_user_prompt
from vera.presentation.stream_projector import StreamProjector
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.presentation.timeline_state import TimelineState
from vera.presentation.tool_activity import ToolActivity
from vera.redaction import Redactor


class TimelineProjector:
    """Pure RuntimeOutput → TimelineMutation projector."""

    def __init__(
        self,
        disclosure: DisclosurePolicy | None = None,
        *,
        max_body_bytes: int = 8_192,
        max_blocks: int = 200,
    ) -> None:
        self.disclosure = disclosure or DisclosurePolicy()
        self._redactor = Redactor()
        self._blocks: dict[str, TimelineBlock] = {}
        self._streams: dict[str, dict[str, object]] = {}
        self._tool_blocks: dict[tuple[str, str], str] = {}
        self._max_body_bytes = max_body_bytes
        self._max_blocks = max_blocks
        self._side_effect_runs: set[str] = set()
        self._model_failures: dict[str, dict[str, object]] = {}
        self._read_activity: ToolActivity | None = None
        self._read_group: str | None = None
        self._read_run = ""
        self._tool_started_at: dict[tuple[str, str], datetime] = {}

    def reset(self) -> None:
        self._read_activity = None
        self._read_group = None
        self._read_run = ""
        self._blocks.clear()
        self._streams.clear()
        self._tool_blocks.clear()
        self._side_effect_runs.clear()
        self._model_failures.clear()
        self._tool_started_at.clear()

    def apply(self, output: RuntimeOutput) -> tuple[TimelineMutation, ...]:
        output = self._redactor.redact_output(output)
        if isinstance(output, StreamFrame):
            return self._apply_stream(output)
        return self._apply_event(output)

    def blocks(self) -> tuple[TimelineBlock, ...]:
        return tuple(self._blocks.values())

    def _apply_stream(self, frame: StreamFrame) -> tuple[TimelineMutation, ...]:
        return StreamProjector.apply(self, frame)

    def _apply_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.apply(self, event)

    def _with_occurred_at(
        self,
        mutations: tuple[TimelineMutation, ...],
        occurred_at: datetime,
    ) -> tuple[TimelineMutation, ...]:
        return TimelineState.with_occurred_at(self, mutations, occurred_at)

    def _side_effects_for(self, run_id: str) -> SideEffectFact:
        return TimelineState.side_effects_for(self, run_id)

    def _unapplied_diffs(self, run_id: str) -> tuple[TimelineMutation, ...]:
        return TimelineState.unapplied_diffs(self, run_id)

    def _relabel_diffs(
        self,
        run_id: str,
        *,
        title: str,
        status: BlockStatus,
    ) -> tuple[TimelineMutation, ...]:
        return TimelineState.relabel_diffs(self, run_id, title=title, status=status)

    def _changeset_applied(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return TimelineState.changeset_applied(self, event)

    def _truncate_body(self, body: str) -> tuple[str, bool]:
        return TimelineState.truncate_body(self, body)

    def _evict_if_needed(self) -> None:
        TimelineState.evict_if_needed(self)

    def _append(
        self,
        *,
        block_id: str,
        run_id: str,
        kind: BlockKind,
        title: str,
        body: str,
        status: BlockStatus,
        focus: bool = False,
        ref_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> tuple[TimelineMutation, ...]:
        return TimelineState.append(
            self,
            block_id=block_id,
            run_id=run_id,
            kind=kind,
            title=title,
            body=body,
            status=status,
            focus=focus,
            ref_id=ref_id,
            occurred_at=occurred_at,
        )

    def _assistant_message(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.assistant_message(self, event)

    def _tool_started(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.tool_started(self, event)

    def _tool_completed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.tool_completed(self, event)

    def _user_prompt(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.user_prompt(self, event)

    def _changeset_proposed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.changeset_proposed(self, event)

    def _session_diff(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.session_diff(self, event)

    def _approval_required(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.approval_required(self, event)

    def _approval_expired(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.approval_expired(self, event)

    def _verification_started(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.verification_started(self, event)

    def _verification_completed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.verification_completed(self, event)

    def _run_failed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.run_failed(self, event)

    def _run_cancelled(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.run_cancelled(self, event)

    def _recovery_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.recovery_event(self, event)

    def _git_operation_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.git_operation_event(self, event)

    def _error_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.error_event(self, event)

    def _terminal_status(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.terminal_status(self, event)

    def _session_status(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.session_status(self, event)

    def _session_doctor(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.session_doctor(self, event)

    def _session_config(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.session_config(self, event)

    def _session_message(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.session_message(self, event)

    def _persistence_warning(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.persistence_warning(self, event)

    def _instruction_status(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.instruction_status(self, event)

    def _skill_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.skill_event(self, event)

    def _session_loaded(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.session_loaded(self, event)

    def _status_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.status_event(self, event)

    def _unknown_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return EventProjector.unknown_event(self, event)


__all__ = [
    "AppendBlock",
    "FocusBlock",
    "TimelineMutation",
    "TimelineProjector",
    "UpdateBlock",
    "project_user_prompt",
]

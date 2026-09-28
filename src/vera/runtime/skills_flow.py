"""Core-owned Skill selection, frozen Run context, and recovery binding."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from vera.content.envelope import ContentEnvelope
from vera.content.trust import ContentTrustLevel
from vera.contracts.events import EventEnvelope
from vera.models.base import ModelMessage
from vera.recovery.hydrator import RecoveryHydrationError
from vera.recovery.models import RecoverySnapshot
from vera.runtime.context import RunContext
from vera.skills.context import SkillContextAssembler, SkillContextError
from vera.skills.selection import SkillSelectionService
from vera.skills.snapshot_store import SkillSnapshotError, SkillSnapshotStore


class SkillsHost(Protocol):
    skill_selection_service: SkillSelectionService | None
    skill_snapshot_store: SkillSnapshotStore
    skill_context_assembler: SkillContextAssembler
    state_dir: Path

    def _prepare_content(
        self,
        context: RunContext,
        text: str,
        *,
        source_kind: str | None,
        origin: str,
        truncated: bool = False,
        trust_level: ContentTrustLevel | None = None,
    ) -> tuple[ContentEnvelope, str, list[EventEnvelope]]: ...


def bind(host: SkillsHost, context: RunContext) -> bool:
    service = host.skill_selection_service
    if service is None or service.pending.mode == "none":
        return False
    selection = service.pending
    if selection.status != "selected":
        raise SkillSnapshotError("skill_selection_invalid", "pending Skill selection is not valid")
    candidate = service.package_for(selection, context.command.workspace_root)
    if candidate is None or candidate.package is None:
        raise SkillSnapshotError("skill_source_changed", "selected Skill is unavailable")
    frozen = host.skill_snapshot_store.freeze(candidate.package, state_dir=host.state_dir)
    context.skill_snapshot = frozen.snapshot
    context.skill_context = host.skill_context_assembler.assemble(frozen)
    consumed = service.consume_for_run(context.command.workspace_root)
    if consumed.status != "selected":
        raise SkillSnapshotError("skill_source_changed", "selected Skill changed before Run")
    return True


def seed(host: SkillsHost, context: RunContext) -> Iterator[EventEnvelope]:
    for part in context.skill_context:
        _envelope, rendered, events = host._prepare_content(
            context,
            part.text,
            source_kind="skill_content",
            origin=part.envelope.origin,
            trust_level=part.envelope.trust_level,
        )
        yield from events
        context.messages.append(ModelMessage(role="user", content=rendered))


def restore(host: SkillsHost, context: RunContext, snapshot: RecoverySnapshot) -> RunContext:
    if snapshot.skill_snapshot is None:
        return context
    try:
        frozen = host.skill_snapshot_store.load(
            snapshot.skill_snapshot.snapshot_id, state_dir=host.state_dir
        )
        if frozen.snapshot != snapshot.skill_snapshot:
            raise SkillSnapshotError("skill_snapshot_corrupt", "recovery facts mismatch")
        context.skill_snapshot = frozen.snapshot
        context.skill_context = host.skill_context_assembler.assemble(frozen)
    except (SkillSnapshotError, SkillContextError) as exc:
        raise RecoveryHydrationError(getattr(exc, "code", "skill_snapshot_corrupt")) from exc
    return context


class SkillsFlow:
    """Stable façade for Core Skill lifecycle steps."""

    bind = staticmethod(bind)
    seed = staticmethod(seed)
    restore = staticmethod(restore)

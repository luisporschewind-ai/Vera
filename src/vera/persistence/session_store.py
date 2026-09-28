"""Conversation session store: the only writer for sessions/ journals."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from vera.contracts import ContractModel
from vera.contracts.conversation import ConversationMessage
from vera.contracts.sessions import (
    ContextCompactedPayload,
    ConversationSessionRecord,
    ConversationTurn,
    SessionClosedPayload,
    SessionCreatedPayload,
    SessionRenamedPayload,
    SkillSelectionChangedSessionPayload,
    TurnCommittedPayload,
)
from vera.contracts.skills import SkillSelection
from vera.persistence.errors import JournalCorrupt, StateVersionError
from vera.persistence.session_journal import SessionJournal
from vera.recovery.probe import workspace_identity
from vera.redaction import Redactor

TITLE_LIMIT = 48
HISTORY_LIMIT = 200


class LoadedConversationSession(ContractModel):
    session_id: str
    workspace_root: Path
    title: str
    records: tuple[ConversationSessionRecord, ...]
    model_messages: tuple[ConversationMessage, ...]
    history_messages: tuple[ConversationMessage, ...]
    compaction_count: int
    skill_selection: SkillSelection
    updated_at: datetime


class ConversationSessionSummary(ContractModel):
    session_id: str
    title: str
    updated_at: datetime
    message_count: int
    latest_run_id: str | None
    latest_run_state: str | None
    recoverable: bool


class SessionRepairPlan(ContractModel):
    source_session_id: str
    valid_through_sequence: int
    failure_code: str
    repairable_tail_only: bool
    source_digest: str


def _new_session_id() -> str:
    return f"session_{uuid4().hex}"


def _now() -> datetime:
    return datetime.now(UTC)


def _title_from_user_text(text: str) -> str:
    line = next((part.strip() for part in text.splitlines() if part.strip()), "新会话")
    if len(line) <= TITLE_LIMIT:
        return line
    return line[:TITLE_LIMIT]


def _record_title(records: tuple[ConversationSessionRecord, ...]) -> str:
    title = "新会话"
    for record in records:
        if record.type == "session.renamed" and isinstance(record.payload, SessionRenamedPayload):
            title = record.payload.title
    return title


def _selection_from_records(records: tuple[ConversationSessionRecord, ...]) -> SkillSelection:
    for record in reversed(records):
        if record.type == "skill.selection.changed" and isinstance(
            record.payload, SkillSelectionChangedSessionPayload
        ):
            return record.payload.selection
    return SkillSelection()


def _messages_from_records(
    records: tuple[ConversationSessionRecord, ...],
) -> tuple[tuple[ConversationMessage, ...], tuple[ConversationMessage, ...], int]:
    history: list[ConversationMessage] = []
    last_compact = 0
    compact_count = 0
    for record in records:
        if record.type == "turn.committed" and isinstance(record.payload, TurnCommittedPayload):
            history.append(ConversationMessage(role="user", content=record.payload.turn.user_text))
            history.append(
                ConversationMessage(role="assistant", content=record.payload.turn.assistant_text)
            )
        elif record.type == "context.compacted" and isinstance(
            record.payload, ContextCompactedPayload
        ):
            compact_count += 1
            last_compact = record.sequence
    model: list[ConversationMessage] = []
    if last_compact:
        compacted = next(
            record
            for record in records
            if record.sequence == last_compact and record.type == "context.compacted"
        )
        assert isinstance(compacted.payload, ContextCompactedPayload)
        model.append(ConversationMessage(role="summary", content=compacted.payload.summary))
        for record in records:
            if record.sequence <= last_compact:
                continue
            if record.type == "turn.committed" and isinstance(record.payload, TurnCommittedPayload):
                turn = record.payload.turn
                model.append(ConversationMessage(role="user", content=turn.user_text))
                model.append(ConversationMessage(role="assistant", content=turn.assistant_text))
    else:
        model = list(history)
    return tuple(history[-HISTORY_LIMIT:]), tuple(model), compact_count


def _latest_run(
    records: tuple[ConversationSessionRecord, ...], state_dir: Path
) -> tuple[str | None, str | None]:
    for record in reversed(records):
        if record.type == "turn.committed" and isinstance(record.payload, TurnCommittedPayload):
            run_id = record.payload.turn.run_id
            if run_id is None:
                return None, None
            if not (state_dir / "runs" / run_id).exists():
                return run_id, "unavailable"
            return run_id, record.payload.turn.terminal_state
    return None, None


class ConversationSessionStore:
    def __init__(
        self,
        state_dir: Path,
        installation_id: str,
        redactor: Redactor | None = None,
        *,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.installation_id = installation_id
        self.redactor = redactor or Redactor([])
        self._id_factory = id_factory or _new_session_id
        self._clock = clock or _now

    def _journal(self, session_id: str) -> SessionJournal:
        if "/" in session_id or "\\" in session_id or session_id in {".", ".."}:
            raise JournalCorrupt("invalid session id", code="invalid_session_record")
        path = self.state_dir / "sessions" / session_id / "session.jsonl"
        return SessionJournal(path, session_id, redactor=self.redactor)

    def _identity(self, workspace: Path) -> str:
        return workspace_identity(workspace, self.installation_id)

    def _next_record(
        self,
        session_id: str,
        record_type: str,
        payload: object,
        sequence: int,
    ) -> ConversationSessionRecord:
        return ConversationSessionRecord(
            session_format_version=1,
            record_id=f"rec_{uuid4().hex}",
            session_id=session_id,
            sequence=sequence,
            timestamp=self._clock(),
            type=record_type,  # type: ignore[arg-type]
            payload=payload,  # type: ignore[arg-type]
        )

    def _loaded(
        self,
        session_id: str,
        records: tuple[ConversationSessionRecord, ...],
        workspace: Path,
    ) -> LoadedConversationSession:
        created = records[0]
        if created.type != "session.created" or not isinstance(
            created.payload, SessionCreatedPayload
        ):
            raise JournalCorrupt("missing session.created", code="invalid_session_record")
        payload = created.payload
        if payload.workspace_identity != self._identity(workspace):
            raise JournalCorrupt("session workspace mismatch", code="session_workspace_mismatch")
        history, model, compact_count = _messages_from_records(records)
        return LoadedConversationSession(
            session_id=session_id,
            workspace_root=Path(payload.workspace_root),
            title=_record_title(records),
            records=records,
            model_messages=model,
            history_messages=history,
            compaction_count=compact_count,
            skill_selection=_selection_from_records(records),
            updated_at=records[-1].timestamp,
        )

    def append_skill_selection(
        self, session_id: str, selection: SkillSelection
    ) -> ConversationSessionRecord:
        journal = self._journal(session_id)
        records = journal.read_all()
        return journal.append(
            self._next_record(
                session_id,
                "skill.selection.changed",
                SkillSelectionChangedSessionPayload(selection=selection),
                (records[-1].sequence if records else 0) + 1,
            )
        )

    def create(self, workspace: Path) -> LoadedConversationSession:
        session_id = self._id_factory()
        root = workspace.expanduser().resolve()
        record = self._next_record(
            session_id,
            "session.created",
            SessionCreatedPayload(
                type="session.created",
                workspace_identity=self._identity(root),
                workspace_root=str(root),
                created_at=self._clock(),
            ),
            1,
        )
        records = (self._journal(session_id).append(record),)
        return self._loaded(session_id, records, root)

    def append_turn(self, session_id: str, turn: ConversationTurn) -> ConversationSessionRecord:
        journal = self._journal(session_id)
        records = journal.read_all()
        sequence = (records[-1].sequence if records else 0) + 1
        committed = journal.append(
            self._next_record(
                session_id,
                "turn.committed",
                TurnCommittedPayload(type="turn.committed", turn=turn),
                sequence,
            )
        )
        if _record_title(records) == "新会话":
            journal.append(
                self._next_record(
                    session_id,
                    "session.renamed",
                    SessionRenamedPayload(
                        type="session.renamed",
                        title=_title_from_user_text(turn.user_text),
                    ),
                    sequence + 1,
                )
            )
        return committed

    def append_compaction(
        self, session_id: str, summary: str, through_sequence: int
    ) -> ConversationSessionRecord:
        journal = self._journal(session_id)
        records = journal.read_all()
        compact_count = sum(1 for record in records if record.type == "context.compacted")
        return journal.append(
            self._next_record(
                session_id,
                "context.compacted",
                ContextCompactedPayload(
                    type="context.compacted",
                    summary=summary,
                    through_sequence=through_sequence,
                    compact_count=compact_count + 1,
                ),
                (records[-1].sequence if records else 0) + 1,
            )
        )

    def rename(self, session_id: str, title: str) -> ConversationSessionRecord:
        journal = self._journal(session_id)
        records = journal.read_all()
        return journal.append(
            self._next_record(
                session_id,
                "session.renamed",
                SessionRenamedPayload(type="session.renamed", title=title),
                (records[-1].sequence if records else 0) + 1,
            )
        )

    def close(self, session_id: str, reason: str) -> ConversationSessionRecord:
        del reason
        journal = self._journal(session_id)
        records = journal.read_all()
        return journal.append(
            self._next_record(
                session_id,
                "session.closed",
                SessionClosedPayload(type="session.closed"),
                (records[-1].sequence if records else 0) + 1,
            )
        )

    def load(self, session_id: str, workspace: Path) -> LoadedConversationSession:
        records = self._journal(session_id).read_all()
        if not records:
            raise JournalCorrupt("session not found", code="session_not_found")
        return self._loaded(session_id, records, workspace.expanduser().resolve())

    def list_for_workspace(self, workspace: Path) -> tuple[ConversationSessionSummary, ...]:
        root = self.state_dir / "sessions"
        if not root.exists():
            return ()
        identity = self._identity(workspace)
        summaries: list[ConversationSessionSummary] = []
        for directory in sorted(root.iterdir()):
            if not directory.is_dir() or directory.is_symlink():
                continue
            journal = SessionJournal(
                directory / "session.jsonl",
                directory.name,
                redactor=self.redactor,
            )
            try:
                inspection = journal.inspect()
            except (JournalCorrupt, StateVersionError, OSError):
                continue
            if not inspection.records:
                continue
            created = inspection.records[0]
            if created.type != "session.created" or not isinstance(
                created.payload, SessionCreatedPayload
            ):
                continue
            if created.payload.workspace_identity != identity:
                continue
            run_id, run_state = _latest_run(inspection.records, self.state_dir)
            history, _model, _count = _messages_from_records(inspection.records)
            summaries.append(
                ConversationSessionSummary(
                    session_id=directory.name,
                    title=_record_title(inspection.records),
                    updated_at=inspection.records[-1].timestamp,
                    message_count=len(history),
                    latest_run_id=run_id,
                    latest_run_state=run_state,
                    recoverable=inspection.failure_code is None,
                )
            )
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return tuple(summaries)

    def latest_for_workspace(self, workspace: Path) -> LoadedConversationSession | None:
        recoverable = [item for item in self.list_for_workspace(workspace) if item.recoverable]
        if not recoverable:
            return None
        return self.load(recoverable[0].session_id, workspace)

    def inspect_repair(self, session_id: str, workspace: Path) -> SessionRepairPlan:
        del workspace
        inspection = self._journal(session_id).inspect()
        if inspection.failure_code is None:
            raise JournalCorrupt(
                "session journal does not need repair",
                code="invalid_session_record",
            )
        return SessionRepairPlan(
            source_session_id=session_id,
            valid_through_sequence=inspection.valid_through_sequence,
            failure_code=inspection.failure_code,
            repairable_tail_only=inspection.repairable_tail_only,
            source_digest=inspection.source_digest,
        )

    def create_repaired_copy(
        self, plan: SessionRepairPlan, workspace: Path
    ) -> LoadedConversationSession:
        if not plan.repairable_tail_only:
            raise JournalCorrupt("session journal requires manual repair", code=plan.failure_code)
        source = self._journal(plan.source_session_id)
        inspection = source.inspect()
        if inspection.source_digest != plan.source_digest:
            raise JournalCorrupt("session repair plan expired", code="invalid_session_record")
        if not inspection.repairable_tail_only:
            raise JournalCorrupt(
                "session journal requires manual repair",
                code=inspection.failure_code or "invalid_session_record",
            )
        original = inspection.raw_bytes
        prefix = tuple(
            record
            for record in inspection.records
            if record.sequence <= plan.valid_through_sequence
        )
        if not prefix:
            raise JournalCorrupt("no valid prefix to repair", code="invalid_session_record")
        new_id = self._id_factory()
        journal = self._journal(new_id)
        for index, record in enumerate(prefix, start=1):
            payload = record.payload
            if index == 1 and isinstance(payload, SessionCreatedPayload):
                payload = payload.model_copy(
                    update={
                        "repaired_from_session_id": plan.source_session_id,
                        "repaired_through_sequence": plan.valid_through_sequence,
                        "source_digest": plan.source_digest,
                    }
                )
            journal.append(
                record.model_copy(
                    update={
                        "session_id": new_id,
                        "sequence": index,
                        "payload": payload,
                        "record_id": f"rec_{uuid4().hex}",
                    }
                )
            )
        if source.path.read_bytes() != original:
            raise JournalCorrupt(
                "source journal changed during repair",
                code="invalid_session_record",
            )
        return self.load(new_id, workspace)

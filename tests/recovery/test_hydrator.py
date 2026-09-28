from pathlib import Path

import pytest

from tests.recovery.helpers import make_snapshot
from vera.contracts.checkpoints import CheckpointFile, CheckpointManifest
from vera.contracts.recovery import RecoveryStage
from vera.persistence.journal import EventJournal
from vera.recovery.hydrator import RecoveryHydrationError, RecoveryHydrator
from vera.recovery.models import PersistedChangeSet
from vera.redaction import Redactor
from vera.runtime.state import RunState


def _journal(tmp_path: Path, run_id: str = "run_1", count: int = 3) -> EventJournal:
    journal = EventJournal(tmp_path / "state", run_id, Redactor([]))
    for index in range(count):
        journal.append("probe", {"index": index})
    return journal


def _write_checkpoint(tmp_path: Path, workspace: Path, run_id: str = "run_1") -> None:
    directory = tmp_path / "state" / "runs" / run_id / "checkpoint"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = CheckpointManifest(
        checkpoint_id="checkpoint_1",
        run_id=run_id,
        workspace_root=workspace,
        before={"app.py": CheckpointFile(existed=True, content_hash="b" * 64, mode=0o644)},
        after_hashes={"app.py": "a" * 64},
    )
    (directory / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")


def test_hydrate_changeset_approval_restores_exact_context(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(workspace)
    journal = _journal(tmp_path)
    context = RecoveryHydrator().hydrate(snapshot, journal)
    assert context.machine.state is RunState.AWAITING_APPROVAL
    assert context.built_change_set == snapshot.built_changeset.to_built()
    assert context.approval_gate.pending_approval == snapshot.pending_approval
    assert context.journal.read_all() == journal.read_all()
    assert context.messages == []
    assert context.security_findings == ()
    assert context.security_context_hash is not None


def test_hydrate_verification_restores_index(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(
        workspace,
        stage=RecoveryStage.VERIFYING,
        pending=False,
        checkpoint_id="checkpoint_1",
        workspace_write_started=True,
        verification_index=1,
    )
    journal = _journal(tmp_path)
    _write_checkpoint(tmp_path, workspace)
    context = RecoveryHydrator().hydrate(snapshot, journal)
    assert context.machine.state is RunState.VERIFYING
    assert context.verification_index == 1
    assert context.workspace_write_started is True


def test_hydrate_refuses_in_flight_verification(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(
        workspace,
        stage=RecoveryStage.VERIFYING,
        pending=False,
        verification_in_flight=True,
        checkpoint_id="checkpoint_1",
        workspace_write_started=True,
    )
    journal = _journal(tmp_path)
    with pytest.raises(RecoveryHydrationError, match="verification_in_flight"):
        RecoveryHydrator().hydrate(snapshot, journal)


def test_hydrate_refuses_sequence_mismatch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(workspace)
    journal = _journal(tmp_path, count=1)
    with pytest.raises(RecoveryHydrationError, match="journal_sequence_mismatch"):
        RecoveryHydrator().hydrate(snapshot, journal)


def test_hydrate_allows_additive_trace_events_after_recovery_snapshot(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(workspace)
    journal = _journal(tmp_path)
    journal.append(
        "trace.span.finished",
        {"trace_id": "run_1", "span_id": "span_1", "status": "ok"},
    )
    journal.append(
        "trace.context.snapshot",
        {
            "trace_id": "run_1",
            "span_id": "span_1",
            "snapshot": {"request_index": 7},
        },
    )

    context = RecoveryHydrator().hydrate(snapshot, journal)

    assert context.machine.state is RunState.AWAITING_APPROVAL
    assert context.trace_recorder is not None
    assert context.request_index == 7


def test_hydrate_still_refuses_non_trace_event_after_recovery_snapshot(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(workspace)
    journal = _journal(tmp_path)
    journal.append("tool.completed", {"call_id": "late"})

    with pytest.raises(RecoveryHydrationError, match="journal_sequence_mismatch"):
        RecoveryHydrator().hydrate(snapshot, journal)


def test_hydrate_refuses_missing_checkpoint(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(
        workspace,
        stage=RecoveryStage.VERIFYING,
        pending=False,
        checkpoint_id="checkpoint_missing",
        workspace_write_started=True,
    )
    journal = _journal(tmp_path)
    with pytest.raises(RecoveryHydrationError, match="checkpoint_missing"):
        RecoveryHydrator().hydrate(snapshot, journal)


def test_hydrate_unavailable_findings_keep_tightening(tmp_path: Path) -> None:
    from vera.content.detector import DetectionDisposition
    from vera.content.envelope import (
        ContentFinding,
        build_content_envelope,
        compute_security_context_hash,
    )
    from vera.policy.engine import PolicyEngine
    from vera.policy.models import PolicyAction, PolicyActionKind, PolicyDecisionKind
    from vera.policy.snapshot import EffectivePolicySnapshot
    from vera.runtime.security import worst_disposition

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    envelope = build_content_envelope("x", source_kind="tool_output", origin="tool")
    finding = ContentFinding(
        envelope=envelope.model_copy(update={"risk_labels": ("detector_unavailable",)}),
        disposition=DetectionDisposition.UNAVAILABLE.value,
        reason_code="detector_error",
        detector_version="unavailable",
    )
    snapshot = make_snapshot(workspace).model_copy(
        update={
            "security_findings": (finding,),
            "security_context_hash": compute_security_context_hash((finding,)),
        }
    )
    journal = _journal(tmp_path)
    context = RecoveryHydrator().hydrate(snapshot, journal)
    assert worst_disposition(context.security_findings) == DetectionDisposition.UNAVAILABLE.value
    decision = PolicyEngine(EffectivePolicySnapshot(workspace_identity="ws")).decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity="ws",
            resource="git",
            argv=("git", "status", "--short"),
            metadata={
                "cwd": ".",
                "detector_disposition": worst_disposition(context.security_findings),
                "risk_labels": ["detector_unavailable"],
            },
        )
    )
    assert decision.decision is PolicyDecisionKind.DENY


def test_hydrate_refuses_intended_hash_mismatch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = make_snapshot(workspace)
    built = snapshot.built_changeset
    assert built is not None
    with pytest.raises(ValueError, match="after_hash mismatch"):
        PersistedChangeSet.model_validate(
            {
                **built.model_dump(mode="json"),
                "intended_content_b64": {"app.py": built.encode_bytes(b"nope\n")},
            }
        )

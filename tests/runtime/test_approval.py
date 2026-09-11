import pytest

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.commands import ResolveApproval
from vera.runtime.approval import ApprovalGate, ApprovalKind, ApprovalMismatch


def test_approval_rejects_changed_target_hash() -> None:
    gate = ApprovalGate(run_id="run_1")
    request = gate.require(ApprovalKind.CHANGESET, "cs_1", "hash_a", "diff", "medium")
    command = ResolveApproval(
        run_id="run_1",
        approval_id=request.approval_id,
        target_hash="hash_b",
        decision="approve",
    )
    with pytest.raises(ApprovalMismatch):
        gate.resolve(command)


def test_approval_is_single_use_and_reject_is_explicit() -> None:
    gate = ApprovalGate(run_id="run_1")
    request = gate.require(ApprovalKind.COMMAND, "cmd_1", "hash", "run", "low")
    command = ResolveApproval(
        run_id="run_1",
        approval_id=request.approval_id,
        target_hash="hash",
        decision="reject",
    )
    assert gate.resolve(command) == "reject"
    with pytest.raises(ApprovalMismatch):
        gate.resolve(command)


def test_approval_rejects_second_pending_request_and_wrong_run() -> None:
    gate = ApprovalGate(run_id="run_1")
    gate.require(ApprovalKind.CHANGESET, "cs_1", "hash", "diff", "high")
    with pytest.raises(ApprovalMismatch):
        gate.require(ApprovalKind.CHANGESET, "cs_2", "hash", "diff", "high")
    other = ApprovalGate(run_id="run_2")
    request = other.require(ApprovalKind.CHANGESET, "cs_1", "hash", "diff", "high")
    with pytest.raises(ApprovalMismatch):
        gate.resolve(
            ResolveApproval(
                run_id="run_2",
                approval_id=request.approval_id,
                target_hash="hash",
                decision="approve",
            )
        )


def test_restored_gate_rejects_wrong_recovery_hash() -> None:
    request = ApprovalRequest(
        approval_id="approval_1",
        run_id="run_1",
        kind="recovery",
        target_id="rec_1",
        target_hash="expected",
        description="restore",
        risk="high",
    )
    gate = ApprovalGate.restore(request)
    with pytest.raises(ApprovalMismatch):
        gate.resolve(
            ResolveApproval(
                run_id="run_1",
                approval_id=request.approval_id,
                target_hash="wrong",
                decision="approve",
            )
        )
    assert (
        gate.resolve(
            ResolveApproval(
                run_id="run_1",
                approval_id=request.approval_id,
                target_hash="expected",
                decision="approve",
            )
        )
        == "approve"
    )

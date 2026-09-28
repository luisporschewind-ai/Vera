import pytest
from pydantic import ValidationError

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.commands import ResolveApproval
from vera.runtime.approval import ApprovalGate, ApprovalKind, ApprovalMismatch
from vera.sandbox.apple_services import APPLE_IOS_BUILD_SERVICES


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


def test_legacy_approval_request_defaults_missing_fact_hash() -> None:
    request = ApprovalRequest.model_validate(
        {
            "schema_version": 1,
            "approval_id": "approval_1",
            "run_id": "run_1",
            "kind": "changeset",
            "target_id": "cs_1",
            "target_hash": "hash",
            "description": "diff",
            "risk": "medium",
        }
    )
    assert request.fact_hash is None
    assert request.security_context_hash is None
    assert request.risk_labels == ()
    assert request.risk_sources == ()
    assert request.schema_version == 1


def test_require_stores_fact_hash() -> None:
    gate = ApprovalGate(run_id="run_1")
    request = gate.require(
        ApprovalKind.CHANGESET,
        "cs_1",
        "hash",
        "diff",
        "medium",
        fact_hash="f" * 64,
    )
    assert request.fact_hash == "f" * 64


def test_require_stores_security_context() -> None:
    from vera.content.envelope import build_content_envelope

    envelope = build_content_envelope("x", source_kind="tool_output", origin="read_file:notes.md")
    gate = ApprovalGate(run_id="run_1")
    request = gate.require(
        ApprovalKind.CHANGESET,
        "cs_1",
        "hash",
        "diff",
        "high",
        security_context_hash="a" * 64,
        risk_labels=("instruction_override",),
        risk_sources=(envelope,),
    )
    assert request.security_context_hash == "a" * 64
    assert request.risk_labels == ("instruction_override",)
    assert request.risk_sources == (envelope,)
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


def test_apple_service_approval_binds_only_the_core_service_set() -> None:
    gate = ApprovalGate(run_id="run_1")
    request = gate.require(
        ApprovalKind.TOOL,
        "action_1",
        "hash",
        "Apple build",
        "high",
        required_capabilities=("apple_ios_build_services",),
        available_scopes=("once",),
    )
    assert request.system_service_names == APPLE_IOS_BUILD_SERVICES

    payload = request.model_dump(mode="json")
    payload["system_service_names"] = ["com.apple.*"]
    with pytest.raises(ValidationError):
        ApprovalRequest.model_validate(payload)

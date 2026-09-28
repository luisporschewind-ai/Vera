from pathlib import Path

from tests.runtime.safe_editing_helpers import (
    _start_edit,
    resolve,
)
from vera.contracts.commands import ResolveApproval, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_changed_path_fact_expires_approval_without_writes(tmp_path: Path) -> None:
    runtime, approval = _start_edit(tmp_path)
    (tmp_path / "hello.txt").write_text("tampered\n", encoding="utf-8")
    follow_up = list(runtime.handle(resolve(approval, "approve")))
    assert follow_up[-1].type == "approval.expired"
    assert follow_up[-1].payload["expiry_reason"] == "fact_changed"
    assert not any(event.type == "checkpoint.created" for event in follow_up)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "tampered\n"


def test_legacy_approval_missing_fact_hash_cannot_authorize_write(tmp_path: Path) -> None:
    runtime, approval = _start_edit(tmp_path)
    context = runtime.runs[approval.run_id]
    pending = context.approval_gate.pending_approval
    assert pending is not None
    context.approval_gate.pending_approval = pending.model_copy(update={"fact_hash": None})
    follow_up = list(runtime.handle(resolve(approval, "approve")))
    checkpoint = tmp_path / "state" / "runs" / approval.run_id / "checkpoint" / "manifest.json"
    assert follow_up[-1].type == "approval.expired"
    assert follow_up[-1].payload["expiry_reason"] == "missing_fact_binding"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert not checkpoint.exists()


def test_unknown_and_cross_run_approvals_fail_closed(tmp_path: Path) -> None:
    runtime, approval = _start_edit(tmp_path)
    unknown = list(
        runtime.handle(
            ResolveApproval(
                run_id=approval.run_id,
                approval_id="approval_missing",
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    assert unknown[-1].type == "approval.expired"
    assert unknown[-1].payload["expiry_reason"] == "unknown_approval"
    other = list(
        runtime.handle(
            ResolveApproval(
                run_id="run_other",
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    assert other[-1].type == "approval.expired"
    assert other[-1].payload["expiry_reason"] == "cross_run"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_reject_and_cancel_do_not_checkpoint_or_write(tmp_path: Path) -> None:
    runtime, approval = _start_edit(tmp_path)
    rejected = list(runtime.handle(resolve(approval, "reject")))
    checkpoint = tmp_path / "state" / "runs" / approval.run_id / "checkpoint" / "manifest.json"
    assert [event.type for event in rejected] == ["approval.resolved", "run.cancelled"]
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert not checkpoint.exists()

    runtime, approval = _start_edit(tmp_path)
    from vera.contracts.commands import CancelRun

    cancelled = list(runtime.handle(CancelRun(run_id=approval.run_id)))
    assert cancelled[-1].type == "run.cancelled"
    assert not any(event.type == "checkpoint.created" for event in cancelled)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_apply_disk_error_never_emits_completed(tmp_path: Path) -> None:
    import errno

    class EnospcWriter:
        def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
            del path, content, mode
            raise OSError(errno.ENOSPC, "No space left on device")

        def delete(self, path: Path) -> None:
            del path
            raise OSError(errno.ENOSPC, "No space left on device")

    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments={
                            "summary": "edit",
                            "changes": [
                                {
                                    "operation": "update",
                                    "path": "hello.txt",
                                    "after_content": "new\n",
                                }
                            ],
                        },
                    ),
                ),
            )
        ]
    )
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        tmp_path / "state",
        file_writer=EnospcWriter(),
    )
    start = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start if event.type == "approval.required")
    events = list(runtime.handle(resolve(approval, "approve")))
    assert not any(event.type == "run.completed" for event in events)
    failed = next(event for event in events if event.type == "run.failed")
    assert failed.payload["reason"] == "no_space"
    apply_event = next(
        event
        for event in events
        if event.type in {"checkpoint.restore_failed", "checkpoint.restored"}
    )
    assert apply_event.payload["written"] is False
    assert apply_event.payload["next_step"] == "restore"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"

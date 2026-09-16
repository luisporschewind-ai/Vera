from pathlib import Path

from pydantic import BaseModel

from vera.contracts.commands import ResolveApproval, RollbackRun, StartRun
from vera.contracts.verification import VerificationCommand
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.command_policy import CommandPolicy
from vera.tools.definitions import ToolResult
from vera.tools.filesystem import read_file
from vera.tools.registry import ToolRegistry
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.paths import WorkspacePaths


class ReadInput(BaseModel):
    path: str


class ReadTool:
    name = "read_file"
    input_model = ReadInput

    def __init__(self, root: Path) -> None:
        self.paths = WorkspacePaths(root)

    def execute(self, arguments: ReadInput) -> ToolResult:
        return read_file(self.paths, arguments.path)


def runtime_with_verification_command(
    tmp_path: Path,
    argv: tuple[str, ...],
    *,
    command_policy: CommandPolicy | None = None,
) -> VeraRuntime:
    return VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="1",
                            name="propose_changeset",
                            arguments={
                                "summary": "edit and verify",
                                "changes": [
                                    {
                                        "operation": "update",
                                        "path": "hello.txt",
                                        "after_content": "new\n",
                                    }
                                ],
                                "verification": [
                                    {
                                        "argv": list(argv),
                                        "cwd": ".",
                                    }
                                ],
                            },
                        ),
                    ),
                )
            ]
        ),
        ToolRegistry(),
        tmp_path / "state",
        command_policy=command_policy,
        artifact_prefix=tmp_path.parent / f"{tmp_path.name}-vera-verification",
        installation_id="install-test",
    )


def runtime_with_approved_verification(tmp_path: Path) -> VeraRuntime:
    return runtime_with_verification_command(tmp_path, ("ruff", "check", "."))


def resolve(event, decision: str) -> ResolveApproval:
    return ResolveApproval(
        run_id=event.run_id,
        approval_id=str(event.payload["approval_id"]),
        target_hash=str(event.payload["target_hash"]),
        decision=decision,
    )


def test_approved_changeset_checkpoints_applies_and_completes(tmp_path: Path) -> None:
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
    registry = ToolRegistry()
    runtime = VeraRuntime(adapter, registry, tmp_path / "state")
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in events if event.type == "approval.required")
    follow_up = list(
        runtime.handle(
            ResolveApproval(
                run_id=str(
                    approval.payload["run_id"] if "run_id" in approval.payload else events[0].run_id
                ),
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    assert [event.type for event in follow_up] == [
        "approval.resolved",
        "checkpoint.created",
        "changeset.applied",
        "run.completed",
    ]
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "new\n"


def test_runtime_rollback_restores_original_bytes(tmp_path: Path) -> None:
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
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in events if event.type == "approval.required")
    list(
        runtime.handle(
            ResolveApproval(
                run_id=events[0].run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    rollback_events = list(runtime.handle(RollbackRun(run_id=events[0].run_id)))
    assert rollback_events[-1].type == "rollback.completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_approved_verification_command_runs_once_and_completes(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = runtime_with_approved_verification(tmp_path)
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    changeset_approval = next(event for event in start_events if event.type == "approval.required")
    apply_events = list(runtime.handle(resolve(changeset_approval, "approve")))
    command_approval = next(event for event in apply_events if event.type == "approval.required")

    command_events = list(runtime.handle(resolve(command_approval, "approve")))

    assert [event.type for event in command_events] == [
        "approval.resolved",
        "verification.completed",
        "run.completed",
    ]
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert not (tmp_path / "verified.txt").exists()
    assert not (tmp_path / "build").exists()
    assert command_events[-1].payload["state"] == "completed"
    completed = next(event for event in command_events if event.type == "verification.completed")
    assert completed.payload["artifact_profile"] == "ruff_no_cache"
    assert completed.payload["artifact_cleanup_status"] == "cleaned"


def test_rejected_verification_command_keeps_change_and_finishes_failed(
    tmp_path: Path,
) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = runtime_with_approved_verification(tmp_path)
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    changeset_approval = next(event for event in start_events if event.type == "approval.required")
    apply_events = list(runtime.handle(resolve(changeset_approval, "approve")))
    command_approval = next(event for event in apply_events if event.type == "approval.required")

    command_events = list(runtime.handle(resolve(command_approval, "reject")))

    assert [event.type for event in command_events] == [
        "approval.resolved",
        "verification.completed",
        "run.completed",
    ]
    assert command_events[-1].payload["state"] == "verification_failed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert not (tmp_path / "verified.txt").exists()


def test_run_started_records_workspace_and_model_profile(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = runtime_with_approved_verification(tmp_path)

    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )

    assert events[0].payload["workspace_root"] == str(tmp_path)
    assert events[0].payload["model_profile"] == "fake"


def test_new_runtime_rolls_back_persisted_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    first_runtime = VeraRuntime(
        FakeModelAdapter(
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
        ),
        ToolRegistry(),
        state_dir,
    )
    start_events = list(
        first_runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    list(first_runtime.handle(resolve(approval, "approve")))
    second_runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir)

    events = list(second_runtime.handle(RollbackRun(run_id=start_events[0].run_id)))

    assert events[-1].type == "rollback.completed"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_new_runtime_persisted_rollback_preserves_later_user_edit(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    first_runtime = VeraRuntime(
        FakeModelAdapter(
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
        ),
        ToolRegistry(),
        state_dir,
    )
    start_events = list(
        first_runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    list(first_runtime.handle(resolve(approval, "approve")))
    (tmp_path / "hello.txt").write_text("user edit\n", encoding="utf-8")
    second_runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir)

    events = list(second_runtime.handle(RollbackRun(run_id=start_events[0].run_id)))

    assert events[-1].type == "rollback.conflicted"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "user edit\n"


def test_runtime_uses_injected_user_allowed_command_prefix(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    policy = CommandPolicy(user_allowed_prefixes=(("ruff", "check"),))
    runtime = runtime_with_verification_command(
        tmp_path,
        ("ruff", "check", "."),
        command_policy=policy,
    )

    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    final_events = list(runtime.handle(resolve(approval, "approve")))

    assert not any(event.type == "approval.required" for event in final_events)
    assert final_events[-1].type == "run.completed"
    assert any(event.type == "verification.completed" for event in final_events)


def test_unisolated_verification_is_rejected_before_changeset(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "should-not-exist.txt"
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = runtime_with_verification_command(
        tmp_path,
        ("rm", "-rf", str(marker)),
    )
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    completed = [event for event in start_events if event.type == "tool.completed"]
    assert completed
    assert completed[0].payload["ok"] is False
    assert completed[0].payload["call_id"] == "1"
    assert completed[0].payload["reason_code"] == "verification_artifact_isolation_unavailable"
    assert not any(event.type == "changeset.proposed" for event in start_events)
    assert not any(event.type == "approval.required" for event in start_events)
    assert not marker.exists()
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"
    context = runtime.runs[start_events[0].run_id]
    tool_messages = [message for message in context.messages if message.role == "tool"]
    assert tool_messages
    assert tool_messages[-1].tool_call_id == "1"
    assert "verification_artifact_isolation_unavailable" in tool_messages[-1].content


def test_unisolated_verification_lets_model_retry_without_thinking_break(
    tmp_path: Path,
) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                reasoning_content="先提出带构建验证的变更",
                tool_calls=(
                    ModelToolCall(
                        call_id="call_bad",
                        name="propose_changeset",
                        arguments={
                            "summary": "edit with unverifiable command",
                            "changes": [
                                {
                                    "operation": "update",
                                    "path": "hello.txt",
                                    "after_content": "new\n",
                                }
                            ],
                            "verification": [{"argv": ["rm", "-rf", "."], "cwd": "."}],
                        },
                    ),
                ),
            ),
            ModelTurn(
                finish_reason="tool_calls",
                reasoning_content="去掉无法隔离的验证后再提",
                tool_calls=(
                    ModelToolCall(
                        call_id="call_ok",
                        name="propose_changeset",
                        arguments={
                            "summary": "edit only",
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
            ),
        ]
    )
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        tmp_path / "state",
        artifact_prefix=tmp_path / "vera-verification",
        installation_id="install-test",
    )
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    assert any(event.type == "approval.required" for event in start_events)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert len(adapter.requests) >= 2
    follow_up = adapter.requests[1]
    assistant = next(
        message
        for message in reversed(follow_up.messages)
        if message.role == "assistant" and message.tool_calls
    )
    assert assistant.reasoning_content == "先提出带构建验证的变更"
    assert assistant.tool_calls[0].call_id == "call_bad"
    tool = next(
        message
        for message in follow_up.messages
        if message.role == "tool" and message.tool_call_id == "call_bad"
    )
    assert "verification_" in tool.content
    assert tool.tool_call_id == "call_bad"


def test_invalid_tool_json_lets_model_retry_without_killing_run(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                reasoning_content="准备提出第五页",
                tool_calls=(
                    ModelToolCall(
                        call_id="call_truncated",
                        name="propose_changeset",
                        arguments={},
                        parse_error="invalid_tool_arguments",
                    ),
                ),
            ),
            ModelTurn(
                finish_reason="tool_calls",
                reasoning_content="改成完整 JSON 再提",
                tool_calls=(
                    ModelToolCall(
                        call_id="call_ok",
                        name="propose_changeset",
                        arguments={
                            "summary": "add fifth page",
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
            ),
        ]
    )
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        tmp_path / "state",
        artifact_prefix=tmp_path / "vera-verification",
        installation_id="install-test",
    )
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    completed = [event for event in start_events if event.type == "tool.completed"]
    assert completed
    assert completed[0].payload["ok"] is False
    assert completed[0].payload["call_id"] == "call_truncated"
    assert completed[0].payload["reason_code"] == "invalid_tool_arguments"
    assert not any(event.type == "run.failed" for event in start_events)
    assert any(event.type == "approval.required" for event in start_events)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"
    follow_up = adapter.requests[1]
    assistant = next(
        message
        for message in reversed(follow_up.messages)
        if message.role == "assistant" and message.tool_calls
    )
    assert assistant.reasoning_content == "准备提出第五页"
    assert assistant.tool_calls[0].call_id == "call_truncated"
    tool = next(
        message
        for message in follow_up.messages
        if message.role == "tool" and message.tool_call_id == "call_truncated"
    )
    assert "invalid_tool_arguments" in tool.content


def test_model_supplied_artifact_plan_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="1",
                            name="propose_changeset",
                            arguments={
                                "summary": "edit and verify",
                                "changes": [
                                    {
                                        "operation": "update",
                                        "path": "hello.txt",
                                        "after_content": "new\n",
                                    }
                                ],
                                "verification": [
                                    {
                                        "argv": ["xcodebuild", "-scheme", "Demo", "build"],
                                        "cwd": ".",
                                        "artifact_plan": {
                                            "schema_version": 1,
                                            "profile": "xcode",
                                            "root": ".",
                                            "cleanup": "always",
                                        },
                                    }
                                ],
                            },
                        ),
                    ),
                )
            ]
        ),
        ToolRegistry(),
        tmp_path / "state",
        artifact_prefix=tmp_path.parent / f"{tmp_path.name}-vera-verification",
        installation_id="install-test",
    )
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    assert not any(
        event.type == "tool.completed" and event.payload.get("ok") is False for event in events
    )
    proposed = next(event for event in events if event.type == "changeset.proposed")
    built = runtime.runs[proposed.run_id].built_change_set
    assert built is not None
    planned = built.change_set.verification[0]
    assert planned.artifact_plan is not None
    assert planned.artifact_plan.profile == "xcode"
    assert Path(planned.artifact_plan.root).is_absolute()
    assert planned.artifact_plan.root != "."
    assert "-derivedDataPath" in planned.argv


def test_forbidden_verification_is_rejected_without_running_or_reclassifying(
    tmp_path: Path,
) -> None:
    test_unisolated_verification_is_rejected_before_changeset(tmp_path)


def test_planned_verification_enters_changeset_and_changes_hash(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = runtime_with_verification_command(tmp_path, ("ruff", "check", "."))
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    run_id = events[0].run_id
    built = runtime.runs[run_id].built_change_set
    assert built is not None
    planned = built.change_set.verification[0]
    assert planned.artifact_plan is not None
    assert planned.argv[-1] == "--no-cache"
    assert planned.artifact_plan.profile == "ruff_no_cache"
    unplanned = ChangeSetBuilder(WorkspacePaths(tmp_path)).build(
        run_id,
        "edit and verify",
        [ChangeProposal(operation="update", path="hello.txt", after_content="new\n")],
        [VerificationCommand(argv=("ruff", "check", "."), cwd=".")],
    )
    assert built.change_set.content_hash != unplanned.change_set.content_hash


def test_command_approval_shows_final_planned_argv_and_profile(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = runtime_with_verification_command(tmp_path, ("ruff", "check", "."))
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    changeset_approval = next(event for event in start_events if event.type == "approval.required")
    apply_events = list(runtime.handle(resolve(changeset_approval, "approve")))
    command_approval = next(event for event in apply_events if event.type == "approval.required")
    pending = runtime.runs[start_events[0].run_id].pending_command
    assert pending is not None
    assert pending.artifact_plan is not None
    assert command_approval.payload["argv"] == list(pending.argv)
    assert command_approval.payload["cwd"] == pending.cwd
    assert command_approval.payload["artifact_profile"] == pending.artifact_plan.profile
    assert command_approval.payload["artifact_root"] == pending.artifact_plan.root
    assert pending.argv == ("ruff", "check", ".", "--no-cache")


def _start_edit(tmp_path: Path) -> tuple[VeraRuntime, object]:
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
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in events if event.type == "approval.required")
    return runtime, approval


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

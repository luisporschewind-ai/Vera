import sys
from pathlib import Path

from pydantic import BaseModel

from vera.contracts.commands import ResolveApproval, RollbackRun, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.command_policy import CommandPolicy
from vera.tools.definitions import ToolResult
from vera.tools.filesystem import read_file
from vera.tools.registry import ToolRegistry
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
    )


def runtime_with_approved_verification(tmp_path: Path) -> VeraRuntime:
    return runtime_with_verification_command(
        tmp_path,
        (
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "p=Path('verified.txt'); "
            "old=p.read_text() if p.exists() else ''; "
            "p.write_text(old + 'x')",
        ),
    )


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
    assert (tmp_path / "verified.txt").read_text(encoding="utf-8") == "x"
    assert command_events[-1].payload["state"] == "completed"


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
    policy = CommandPolicy(user_allowed_prefixes=((sys.executable, "-c"),))
    runtime = runtime_with_verification_command(
        tmp_path,
        (sys.executable, "-c", "print('verified')"),
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

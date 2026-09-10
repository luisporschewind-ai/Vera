from pathlib import Path

from pydantic import BaseModel

from vera.contracts.commands import ResolveApproval, RollbackRun, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
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

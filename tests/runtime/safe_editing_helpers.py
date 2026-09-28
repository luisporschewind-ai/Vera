from pathlib import Path

from pydantic import BaseModel

from vera.contracts.commands import ResolveApproval, StartRun
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

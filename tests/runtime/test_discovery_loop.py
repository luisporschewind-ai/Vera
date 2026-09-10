from pathlib import Path

from pydantic import BaseModel

from vera.contracts.commands import StartRun
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
    description = "read a UTF-8 file"
    input_model = ReadInput

    def __init__(self, root: Path) -> None:
        self.paths = WorkspacePaths(root)

    def execute(self, arguments: ReadInput) -> ToolResult:
        return read_file(self.paths, arguments.path)


def test_runtime_reaches_changeset_approval_without_writing(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(call_id="1", name="read_file", arguments={"path": "hello.txt"}),
                ),
            ),
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="2",
                        name="propose_changeset",
                        arguments={
                            "summary": "update hello",
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
    registry = ToolRegistry()
    registry.register(ReadTool(tmp_path))
    events = list(
        VeraRuntime(adapter, registry, tmp_path / "state").handle(
            StartRun(goal="update hello", workspace_root=tmp_path, model_profile="fake")
        )
    )
    assert [event.type for event in events][-2:] == ["changeset.proposed", "approval.required"]
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert all("provider" not in str(event.payload) for event in events)

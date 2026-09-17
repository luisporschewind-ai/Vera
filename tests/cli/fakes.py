from pathlib import Path

from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def make_two_approval_runtime(workspace: Path, state_dir: Path) -> VeraRuntime:
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="proposal-1",
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
                                    "argv": ["ruff", "check", "."],
                                    "cwd": ".",
                                }
                            ],
                        },
                    ),
                ),
            )
        ]
    )
    return VeraRuntime(
        adapter,
        ToolRegistry(),
        state_dir,
        artifact_prefix=state_dir.parent / "vera-verification",
    )


def make_changeset_runtime(workspace: Path, state_dir: Path) -> VeraRuntime:
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="proposal-1",
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
    return VeraRuntime(adapter, ToolRegistry(), state_dir)

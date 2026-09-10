from pathlib import Path

from vera.contracts.commands import ResolveApproval, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry

from .helpers import git, make_repo


def test_rejection_preserves_git_fixture(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
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
        tmp_path / "state",
    )
    events = list(runtime.handle(StartRun(goal="edit", workspace_root=repo, model_profile="fake")))
    approval = next(event for event in events if event.type == "approval.required")
    rejected = list(
        runtime.handle(
            ResolveApproval(
                run_id=events[0].run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="reject",
            )
        )
    )
    assert rejected[-1].type == "run.cancelled"
    assert (repo / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert git(repo, "status", "--short") == ""

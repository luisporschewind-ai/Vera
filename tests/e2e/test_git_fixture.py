from pathlib import Path

from vera.contracts.commands import ResolveApproval, RollbackRun, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry

from .helpers import git, make_repo


def test_full_safe_editing_and_rollback_in_git_fixture(tmp_path: Path) -> None:
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
                                "summary": "把 hello 改为 new",
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
    start_events = list(
        runtime.handle(
            StartRun(goal="把 hello 改为 new", workspace_root=repo, model_profile="fake")
        )
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    list(
        runtime.handle(
            ResolveApproval(
                run_id=start_events[0].run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    assert (repo / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert git(repo, "diff", "--", "hello.txt")
    rollback = list(runtime.handle(RollbackRun(run_id=start_events[0].run_id)))
    assert rollback[-1].type == "rollback.completed"
    assert (repo / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert git(repo, "status", "--short") == ""

from pathlib import Path

from tests.runtime.safe_editing_helpers import (
    resolve,
    runtime_with_verification_command,
)
from vera.contracts.commands import StartRun
from vera.contracts.verification import VerificationCommand
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.paths import WorkspacePaths


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


def test_missing_verification_executable_is_rejected_before_changeset(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("vera.verification.artifacts.shutil.which", lambda _name: None)
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = runtime_with_verification_command(tmp_path, ("ruff", "check", "webstats.py"))
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    completed = [event for event in start_events if event.type == "tool.completed"]
    assert completed
    assert completed[0].payload["ok"] is False
    assert completed[0].payload["reason_code"] == "verification_executable_missing"
    assert not any(event.type == "changeset.proposed" for event in start_events)
    assert not any(event.type == "approval.required" for event in start_events)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"


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

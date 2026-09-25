from pathlib import Path

from vera.contracts.commands import CancelRun, StartRun
from vera.contracts.conversation import ConversationMessage
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_compaction_uses_no_tools_and_emits_summary(tmp_path: Path) -> None:
    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="保留结论：使用 Python Core。", finish_reason="stop")]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    command = StartRun(
        goal="保留架构决策",
        workspace_root=tmp_path,
        model_profile="fake",
        mode="compact",
        conversation=(
            ConversationMessage(role="user", content="Core 用什么语言？"),
            ConversationMessage(role="assistant", content="使用 Python。"),
        ),
    )

    events = list(runtime.handle(command))

    assert adapter.requests[0].tools == ()
    assert adapter.requests[0].messages[0].role == "system"
    user = next(message for message in adapter.requests[0].messages if message.role == "user")
    assert '"vera_content":1' in user.content
    assert (
        next(event for event in events if event.type == "run.started").payload["kind"]
        == "compaction"
    )
    assert (
        next(event for event in events if event.type == "conversation.compacted").payload["summary"]
        == "保留结论：使用 Python Core。"
    )
    assert events[-1].payload["outcome"] == "compacted"


def test_compaction_empty_summary_fails(tmp_path: Path) -> None:
    adapter = FakeModelAdapter([ModelTurn(assistant_text="   ", finish_reason="stop")])
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = list(
        runtime.handle(
            StartRun(
                goal="focus",
                workspace_root=tmp_path,
                model_profile="fake",
                mode="compact",
                conversation=(
                    ConversationMessage(role="user", content="hello"),
                    ConversationMessage(role="assistant", content="hi"),
                ),
            )
        )
    )

    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "empty_model_response"


def test_compaction_drops_leaked_tool_markup(tmp_path: Path) -> None:
    summaries = [
        '保留结论：使用 Python。<｜DSML｜invoke name="read_file">',
        '<｜DSML｜invoke name="read_file">',
    ]
    outcomes = []
    for index, summary in enumerate(summaries):
        adapter = FakeModelAdapter([ModelTurn(assistant_text=summary, finish_reason="stop")])
        runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / f"state-{index}")
        outcomes.append(
            list(
                runtime.handle(
                    StartRun(
                        goal="focus",
                        workspace_root=tmp_path,
                        model_profile="fake",
                        mode="compact",
                        conversation=(ConversationMessage(role="user", content="hello"),),
                    )
                )
            )
        )

    kept, empty = outcomes
    assert (
        next(event for event in kept if event.type == "conversation.compacted").payload["summary"]
        == "保留结论：使用 Python。"
    )
    assert empty[-1].type == "run.failed"
    assert empty[-1].payload["reason"] == "empty_model_response"


def test_compaction_rejects_tool_calls(tmp_path: Path) -> None:
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(call_id="1", name="read_file", arguments={"path": "a.txt"}),
                ),
            )
        ]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = list(
        runtime.handle(
            StartRun(
                goal="focus",
                workspace_root=tmp_path,
                model_profile="fake",
                mode="compact",
                conversation=(ConversationMessage(role="user", content="hello"),),
            )
        )
    )

    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "invalid_compaction_response"
    assert adapter.requests[0].tools == ()


def test_agent_run_started_kind_is_task(tmp_path: Path) -> None:
    adapter = FakeModelAdapter([ModelTurn(assistant_text="ok", finish_reason="stop")])
    events = list(
        VeraRuntime(adapter, ToolRegistry(), tmp_path / "state").handle(
            StartRun(goal="Hello", workspace_root=tmp_path, model_profile="fake")
        )
    )
    assert next(event for event in events if event.type == "run.started").payload["kind"] == "task"


def test_cancel_after_compaction_replays_without_second_journal_event(tmp_path: Path) -> None:
    from vera.persistence.journal import EventJournal
    from vera.redaction import Redactor

    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="保留决策：使用 Python。", finish_reason="stop")]
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    started = list(
        runtime.handle(
            StartRun(
                goal="保留架构决策",
                workspace_root=tmp_path,
                model_profile="fake",
                mode="compact",
                conversation=(
                    ConversationMessage(role="user", content="Core 用什么语言？"),
                    ConversationMessage(role="assistant", content="使用 Python。"),
                ),
            )
        )
    )
    run_id = started[0].run_id
    first = list(runtime.handle(CancelRun(run_id=run_id)))
    second = list(runtime.handle(CancelRun(run_id=run_id)))
    journal = EventJournal(tmp_path / "state", run_id, Redactor([]))
    assert sum(1 for event in journal.read_all() if event.type == "run.cancelled") == 1
    assert first[-1].type == "run.cancelled"
    assert second[-1].type == "run.cancelled"

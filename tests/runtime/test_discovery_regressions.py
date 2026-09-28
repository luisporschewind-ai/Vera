import json
from pathlib import Path

from vera.config import Limits
from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelMessage, ModelToolCall, ModelTurn
from vera.runtime.context import compact_run_messages
from vera.runtime.engine import VeraRuntime
from vera.tools.builtin import ReadTool
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


def test_small_history_is_not_evicted_after_eight_results() -> None:
    messages = [ModelMessage(role="user", content="inspect files")]
    for i in range(12):
        call = ModelToolCall(call_id=str(i), name="read", arguments={"path": f"{i}.txt"})
        messages.extend(
            [
                ModelMessage(role="assistant", content="", tool_calls=(call,)),
                ModelMessage(role="tool", content="tiny", tool_call_id=str(i)),
            ]
        )
    result = compact_run_messages(messages, max_bytes=200_000)
    assert [m.tool_call_id for m in result if m.role == "tool"] == [str(i) for i in range(12)]


def test_body_compaction_keeps_outcome_and_marks_omission() -> None:
    call = ModelToolCall(call_id="a", name="read", arguments={"path": "a.txt"})
    messages = [
        ModelMessage(role="assistant", content="", tool_calls=(call,)),
        ModelMessage(
            role="tool",
            tool_call_id="a",
            content=json.dumps(
                {
                    "data": "x" * 10_000,
                    "ok": True,
                    "origin": "read:a.txt",
                    "truncated": False,
                }
            ),
        ),
    ]
    result = compact_run_messages(messages, max_bytes=2000)
    payload = json.loads(next(m.content for m in result if m.role == "tool"))
    assert payload["ok"] is True
    assert payload["body_omitted"] is True
    assert payload["origin"] == "read:a.txt"
    assert payload["data"] == ""


def test_alternating_unchanged_reads_warn_then_stop(tmp_path: Path) -> None:
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text(name)
    registry = ToolRegistry()
    registry.register(ReadTool(WorkspacePaths(tmp_path), 1000))
    turns = [
        ModelTurn(
            finish_reason="tool_calls",
            tool_calls=(
                ModelToolCall(
                    call_id=str(i),
                    name="read",
                    arguments={"path": ("a.txt", "b.txt")[i % 2]},
                ),
            ),
        )
        for i in range(20)
    ]
    runtime = VeraRuntime(
        FakeModelAdapter(turns), registry, tmp_path / "state", limits=Limits(max_model_turns=25)
    )
    events = list(
        runtime.handle(StartRun(goal="inspect", workspace_root=tmp_path, model_profile="fake"))
    )
    assert any(e.type == "tool.repetition_detected" for e in events)
    assert events[-1].payload.get("reason") == "read_loop_no_progress"
    assert sum(e.type == "tool.completed" for e in events) < 20


def test_compaction_preserves_evicted_execution_metadata() -> None:
    messages = []
    for i in range(4):
        call = ModelToolCall(call_id=str(i), name="read", arguments={"path": f"{i}.txt"})
        messages.extend(
            [
                ModelMessage(role="assistant", content="", tool_calls=(call,)),
                ModelMessage(
                    role="tool",
                    tool_call_id=str(i),
                    content=json.dumps(
                        {
                            "ok": True,
                            "data": "FILE_BODY_MUST_NOT_ENTER_HISTORY" * 100,
                            "content_hash": str(i),
                            "core_approval": {"decision": "approve"},
                        }
                    ),
                ),
            ]
        )
    compacted = compact_run_messages(messages, max_bytes=4000, max_tool_messages=2)
    notice = next(json.loads(m.content) for m in compacted if m.role == "user")
    assert notice["core_execution_history"][0]["target"] == "0.txt"
    assert notice["core_execution_history"][0]["ok"] is True
    assert "FILE_BODY" not in json.dumps(notice)
    again = compact_run_messages(compacted, max_bytes=4000)
    assert sum("core_execution_history" in m.content for m in again) == 1


def test_read_progress_resets_on_changed_output_and_mutation() -> None:
    from types import SimpleNamespace

    from vera.runtime.read_progress import observe_read

    context = SimpleNamespace(read_observations={}, unchanged_read_streak=0)
    call = ModelToolCall(call_id="a", name="read", arguments={"path": "a.txt"})
    for _ in range(4):
        observe_read(context, call, "before", True)
    assert context.unchanged_read_streak == 3
    assert not observe_read(context, call, "after", True)
    assert context.unchanged_read_streak == 0
    observe_read(context, call, "after", True)
    write = ModelToolCall(call_id="w", name="edit", arguments={"path": "a.txt"})
    observe_read(context, write, "mutation", True)
    assert not observe_read(context, call, "after", True)
    assert context.unchanged_read_streak == 0


def test_parallel_repeat_warning_keeps_tool_results_paired(tmp_path: Path) -> None:
    from vera.runtime.context import normalize_tool_transcript

    (tmp_path / "a.txt").write_text("a")
    registry = ToolRegistry()
    registry.register(ReadTool(WorkspacePaths(tmp_path), 1000))
    turns = [
        ModelTurn(
            finish_reason="tool_calls",
            tool_calls=tuple(
                ModelToolCall(call_id=f"{r}-{i}", name="read", arguments={"path": "a.txt"})
                for i in range(3)
            ),
        )
        for r in range(2)
    ] + [ModelTurn(assistant_text="done", finish_reason="stop")]
    adapter = FakeModelAdapter(turns)
    events = list(
        VeraRuntime(adapter, registry, tmp_path / "state").handle(
            StartRun(goal="inspect", workspace_root=tmp_path, model_profile="fake")
        )
    )
    assert events[-1].type == "run.completed"
    # FakeModelAdapter captures the actual requests consumed by the loop.
    for request in adapter.requests:
        assert normalize_tool_transcript(list(request.messages)) == list(request.messages)

"""Runtime model resilience tests."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelTurn, ModelUsage
from vera.models.capabilities import ModelCapabilities
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.retry import RetryPolicy
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_transient_failure_retries_once_without_repeating_tools(tmp_path: Path) -> None:
    sleeps: list[float] = []
    workspace = tmp_path / "ws"
    workspace.mkdir()
    adapter = FakeModelAdapter(
        [
            ModelProviderError(ModelErrorCode.TIMEOUT, "timeout"),
            ModelTurn(
                assistant_text="ok",
                finish_reason="stop",
                usage=ModelUsage(input_tokens=20, output_tokens=4, total_tokens=24),
            ),
        ]
    )
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        tmp_path / "state",
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.25),
        sleep=sleeps.append,
    )
    events = tuple(
        runtime.handle(StartRun(goal="hi", workspace_root=workspace, model_profile="fake"))
    )
    assert [event.type for event in events].count("model.retrying") == 1
    assert len(adapter.requests) == 2
    assert not any(event.type == "tool.started" for event in events)
    assert sleeps == [0.25]
    assert events[-1].type == "run.completed"
    context = runtime.runs[events[0].run_id]
    trace_events = context.journal.read_all()
    started = [event for event in trace_events if event.type == "trace.span.started"]
    finished = [event for event in trace_events if event.type == "trace.span.finished"]
    snapshots = [event for event in trace_events if event.type == "trace.context.snapshot"]
    assert len(started) == len(finished) == len(snapshots) == 2
    assert started[0].payload["span_id"] != started[1].payload["span_id"]
    assert started[1].payload["attributes"]["retry_of_span_id"] == started[0].payload["span_id"]
    assert [event.payload["snapshot"]["request_index"] for event in snapshots] == [1, 2]
    assert all(event.payload["snapshot"]["message_count"] > 0 for event in snapshots)
    assert [
        event.payload["span_id"] for event in trace_events if event.type == "model.requested"
    ] == [event.payload["span_id"] for event in started]
    completed = next(event for event in trace_events if event.type == "model.completed")
    successful_span = next(
        event
        for event in trace_events
        if event.type == "trace.span.finished" and event.payload["status"] == "ok"
    )
    assert completed.payload["span_id"] == successful_span.payload["span_id"]
    assert completed.payload["usage"] == {
        "input_tokens": 20,
        "output_tokens": 4,
        "total_tokens": 24,
        "cache_hit_input_tokens": None,
        "cache_miss_input_tokens": None,
    }
    assert successful_span.payload["attributes"]["total_tokens"] == 24
    trace_text = "\n".join(
        str(event.payload) for event in trace_events if event.type.startswith("trace.")
    )
    assert "initial user goal secret" not in trace_text


def test_auth_failure_does_not_retry(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sleeps: list[float] = []
    adapter = FakeModelAdapter(
        [ModelProviderError(ModelErrorCode.AUTHENTICATION, "auth", status_code=401)]
    )
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        tmp_path / "state",
        retry_policy=RetryPolicy(max_attempts=2),
        sleep=sleeps.append,
    )
    events = tuple(
        runtime.handle(StartRun(goal="hi", workspace_root=workspace, model_profile="fake"))
    )
    assert any(event.type == "model.failed" for event in events)
    assert not any(event.type == "model.retrying" for event in events)
    assert sleeps == []
    assert len(adapter.requests) == 1
    context = runtime.runs[events[0].run_id]
    finished = [
        event for event in context.journal.read_all() if event.type == "trace.span.finished"
    ]
    assert len(finished) == 1
    assert finished[0].payload["status"] == "error"


def test_capability_mismatch_fails_before_adapter_call(tmp_path: Path) -> None:
    adapter = FakeModelAdapter(
        [],
        capabilities=ModelCapabilities(tool_calling=False),
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    events = tuple(
        runtime.handle(StartRun(goal="edit", workspace_root=workspace, model_profile="fake"))
    )
    assert any(event.type == "model.failed" for event in events)
    assert adapter.requests == []
    context = runtime.runs[events[0].run_id]
    assert not any(event.type == "trace.span.started" for event in context.journal.read_all())


def test_missing_stream_completion_finishes_attempt_span_as_error(tmp_path: Path) -> None:
    class EmptyStreamAdapter(FakeModelAdapter):
        def stream(self, request):  # noqa: ANN001, ANN201
            del request
            return iter(())

    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime = VeraRuntime(EmptyStreamAdapter(), ToolRegistry(), tmp_path / "state")
    events = tuple(
        runtime.handle(StartRun(goal="hi", workspace_root=workspace, model_profile="fake"))
    )
    context = runtime.runs[events[0].run_id]
    finished = [
        event for event in context.journal.read_all() if event.type == "trace.span.finished"
    ]
    assert len(finished) == 1
    assert finished[0].payload["status"] == "error"

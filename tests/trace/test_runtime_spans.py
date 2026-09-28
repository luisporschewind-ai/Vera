from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from vera.contracts.commands import ResolveApproval, StartRun
from vera.contracts.verification import VerificationCommand, VerificationResult
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.definitions import ToolResult
from vera.tools.registry import ToolRegistry


class _ReadInput(BaseModel):
    path: str


class _ReadTool:
    name = "read_file"
    input_model = _ReadInput

    def __init__(self, content: str = "private-file-body") -> None:
        self.content = content

    def execute(self, arguments: _ReadInput) -> ToolResult:
        return ToolResult(ok=True, content={"content": self.content})


def _tool_call(name: str, arguments: dict[str, object], *, parse_error: str | None = None):
    return ModelToolCall(
        call_id="call-secret-id",
        name=name,
        arguments=arguments,
        parse_error=parse_error,
    )


def _run_tool(tmp_path: Path, call: ModelToolCall, tool: object):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register(tool)  # type: ignore[arg-type]
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(finish_reason="tool_calls", tool_calls=(call,)),
                ModelTurn(assistant_text="done", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
    )
    events = tuple(
        runtime.handle(StartRun(goal="inspect", workspace_root=workspace, model_profile="fake"))
    )
    context = runtime.runs[events[0].run_id]
    return events, context


def test_tool_span_records_hashes_sizes_and_links_business_events(tmp_path: Path) -> None:
    call = _tool_call("read_file", {"path": "secret.txt"})
    events, context = _run_tool(tmp_path, call, _ReadTool())
    journal = context.journal.read_all()
    started = next(
        event
        for event in journal
        if event.type == "trace.span.started" and event.payload["kind"] == "tool"
    )
    finished = next(
        event
        for event in journal
        if event.type == "trace.span.finished" and event.payload["kind"] == "tool"
    )
    business_started = next(event for event in journal if event.type == "tool.started")
    business_finished = next(event for event in journal if event.type == "tool.completed")
    input_bytes = json.dumps(
        call.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    output_text = next(
        message.content
        for message in reversed(context.messages)
        if message.role == "tool" and message.tool_call_id == call.call_id
    )

    assert business_started.payload["span_id"] == business_finished.payload["span_id"]
    assert business_started.payload["span_id"] == started.payload["span_id"]
    assert business_finished.payload["span_id"] == finished.payload["span_id"]
    assert started.payload["attributes"]["input_byte_count"] == len(input_bytes)
    assert (
        started.payload["attributes"]["input_content_hash"]
        == hashlib.sha256(input_bytes).hexdigest()
    )
    assert finished.payload["attributes"]["output_byte_count"] == len(output_text.encode())
    assert (
        finished.payload["attributes"]["output_content_hash"]
        == hashlib.sha256(output_text.encode()).hexdigest()
    )
    trace_text = "\n".join(
        str(event.payload) for event in journal if event.type.startswith("trace.")
    )
    assert "private-file-body" not in trace_text
    assert "secret.txt" not in trace_text
    assert events[-1].type == "run.completed"


def test_rejected_tool_call_finishes_rejected_span(tmp_path: Path) -> None:
    call = _tool_call("read_file", {}, parse_error="invalid_arguments")
    _events, context = _run_tool(tmp_path, call, _ReadTool())
    journal = context.journal.read_all()
    started = next(event for event in journal if event.type == "tool.started")
    completed = next(event for event in journal if event.type == "tool.completed")
    finished = next(
        event
        for event in journal
        if event.type == "trace.span.finished" and event.payload["kind"] == "tool"
    )

    assert started.payload["span_id"] == completed.payload["span_id"]
    assert completed.payload["span_id"] == finished.payload["span_id"]
    assert finished.payload["status"] == "rejected"
    assert finished.payload["attributes"]["error_code"] == "invalid_arguments"


class _RaisingTool(_ReadTool):
    def execute(self, arguments: _ReadInput) -> ToolResult:
        del arguments
        raise RuntimeError("private exception body")


def test_tool_exception_finishes_error_span_without_exception_body(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register(_RaisingTool())
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls", tool_calls=(_tool_call("read_file", {"path": "x"}),)
                )
            ]
        ),
        registry,
        tmp_path / "state",
    )
    stream = runtime.handle(
        StartRun(goal="inspect", workspace_root=workspace, model_profile="fake")
    )
    with pytest.raises(RuntimeError, match="private exception body"):
        tuple(stream)
    context = next(iter(runtime.runs.values()))
    finished = next(
        event
        for event in context.journal.read_all()
        if event.type == "trace.span.finished" and event.payload["kind"] == "tool"
    )
    assert finished.payload["status"] == "error"
    assert "private exception body" not in str(finished.payload)


def test_verification_spans_only_actual_runs_and_omits_output_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("before", encoding="utf-8")
    proposal = ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            _tool_call(
                "propose_changeset",
                {
                    "summary": "change",
                    "changes": [{"operation": "update", "path": "a.txt", "after_content": "after"}],
                    "verification": [{"argv": ["pytest", "-q"], "cwd": "."}],
                },
            ),
        ),
    )
    runtime = VeraRuntime(
        FakeModelAdapter([proposal]), ToolRegistry(), tmp_path / "state", installation_id="test"
    )
    start = tuple(
        runtime.handle(StartRun(goal="edit", workspace_root=workspace, model_profile="fake"))
    )
    changeset_approval = next(event for event in start if event.type == "approval.required")
    applied = tuple(
        runtime.handle(
            ResolveApproval(
                run_id=changeset_approval.run_id,
                approval_id=str(changeset_approval.payload["approval_id"]),
                target_hash=str(changeset_approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    command_approval = next(event for event in applied if event.type == "approval.required")
    context = runtime.runs[changeset_approval.run_id]
    result = VerificationResult(
        argv=("pytest", "-q"),
        cwd=".",
        started_at=datetime(2026, 9, 26, tzinfo=UTC),
        completed_at=datetime(2026, 9, 26, 0, 0, 1, tzinfo=UTC),
        duration_seconds=1.0,
        exit_code=0,
        stdout="private verification output",
        stderr="",
        status="passed",
        artifact_profile="pytest",
        artifact_cleanup_status="cleaned",
    )

    class _Runner:
        def run(self, command):  # noqa: ANN001
            return result.model_copy(update={"argv": command.argv, "cwd": command.cwd})

    monkeypatch.setattr(runtime, "_verification_runner", lambda _context: _Runner())
    completed_events = tuple(
        runtime.handle(
            ResolveApproval(
                run_id=command_approval.run_id,
                approval_id=str(command_approval.payload["approval_id"]),
                target_hash=str(command_approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )

    trace_events = [
        event for event in context.journal.read_all() if event.type.startswith("trace.")
    ]
    finished = next(
        event
        for event in trace_events
        if event.type == "trace.span.finished" and event.payload["kind"] == "verification"
    )
    completed = next(event for event in completed_events if event.type == "verification.completed")
    assert completed.payload["span_id"] == finished.payload["span_id"]
    assert finished.payload["status"] == "ok"
    assert finished.payload["attributes"]["reported_duration_ms"] == 1000.0
    assert finished.payload["attributes"]["stdout_byte_count"] == len(result.stdout.encode())
    assert finished.payload["attributes"]["artifact_cleanup_status"] == "cleaned"
    assert "private verification output" not in str(trace_events)


@pytest.mark.parametrize(
    ("result_status", "span_status"),
    [
        ("passed", "ok"),
        ("failed", "error"),
        ("timed_out", "error"),
        ("cancelled", "cancelled"),
        ("rejected", "rejected"),
        ("workspace_polluted", "error"),
        ("error", "error"),
    ],
)
def test_verification_span_maps_runner_outcomes_and_result_duration(
    tmp_path: Path, result_status: str, span_status: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = VeraRuntime(
        FakeModelAdapter([ModelTurn(assistant_text="done", finish_reason="stop")]),
        ToolRegistry(),
        tmp_path / "state",
    )
    outputs = tuple(
        runtime.handle(StartRun(goal="inspect", workspace_root=workspace, model_profile="fake"))
    )
    context = runtime.runs[outputs[0].run_id]
    command = VerificationCommand(argv=("pytest", "-q"))
    span = runtime._start_verification_span(context, 1, command)
    result = VerificationResult(
        argv=command.argv,
        cwd=command.cwd,
        started_at=datetime(2026, 9, 26, tzinfo=UTC),
        completed_at=datetime(2026, 9, 26, 0, 0, 1, tzinfo=UTC),
        duration_seconds=0.75,
        exit_code=0 if result_status == "passed" else 1,
        stdout="",
        stderr="",
        status=result_status,  # type: ignore[arg-type]
    )

    runtime._finish_verification_span(context, span, result)

    finished = next(
        event
        for event in context.journal.read_all()
        if event.type == "trace.span.finished" and event.payload["span_id"] == span.span_id
    )
    assert finished.payload["status"] == span_status
    assert finished.payload["duration_ms"] == 750.0

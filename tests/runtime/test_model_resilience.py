"""Runtime model resilience tests."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelTurn
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
            ModelTurn(assistant_text="ok", finish_reason="stop"),
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

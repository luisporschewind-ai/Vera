from datetime import UTC, datetime
from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_plain_session import PlainSessionDriver
from vera.cli_session import InteractiveSession, _structured_plain
from vera.config import Limits, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.tools.registry import ToolRegistry


class ScriptedIO:
    def __init__(self, inputs: list[str]) -> None:
        self.inputs = inputs
        self.output: list[str] = []

    def read(self, prompt: str) -> str:
        self.output.append(prompt)
        if not self.inputs:
            raise EOFError
        return self.inputs.pop(0)

    def write(self, text: str) -> None:
        self.output.append(text)

    def clear(self) -> None:
        return None


def test_plain_usage_shows_cache_facts_without_changing_existing_totals() -> None:
    line = _structured_plain(
        "session.usage",
        {
            "calls": 1,
            "input_tokens": 20,
            "output_tokens": 2,
            "total_tokens": 22,
            "cache_hit_input_tokens": 10,
            "cache_miss_input_tokens": 10,
            "cache_hit_percent": 50.0,
        },
    )
    assert "calls 1\tinput 20\toutput 2\ttotal 22" in line
    assert "cache_hit_input_tokens 10" in line
    assert "cache_hit_percent 50.0" in line


def test_plain_session_displays_trace_text_without_projecting_cli_json(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = tmp_path / "state"
    deps = RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir),
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
    )
    io = ScriptedIO([])
    session = InteractiveSession(deps, workspace, "fake", io)
    event = EventEnvelope(
        event_id="event_trace",
        run_id="session_run",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="session.trace",
        payload={"trace": {"run_id": "run_1"}, "text": "Run ID: run_1\n状态: 已完成"},
    )

    session._present_session_event(event)

    assert io.output == ["Run ID: run_1\n状态: 已完成"]


def test_plain_driver_uses_session_controller(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deps = RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state"),
        config=VeraConfig(state_dir=tmp_path / "state", limits=Limits(), providers={}),
    )
    io = ScriptedIO(["/exit"])
    driver = PlainSessionDriver(deps, workspace, "fake", io)
    assert isinstance(driver.session, InteractiveSession)
    assert driver.run() == 0


def test_plain_session_queues_while_run_active(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deps = RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state"),
        config=VeraConfig(state_dir=tmp_path / "state", limits=Limits(), providers={}),
    )
    controller = SessionController(deps, workspace, "fake")
    controller.mark_active("run_1")
    io = ScriptedIO(["later"])
    driver = PlainSessionDriver(deps, workspace, "fake", io, controller=controller)
    assert driver.run() == 0
    assert any("排队" in line for line in io.output)
    assert controller.queued_prompt == "later"


def test_plain_help_and_doctor_share_session_events(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deps = RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state"),
        config=VeraConfig(state_dir=tmp_path / "state", limits=Limits(), providers={}),
    )
    controller = SessionController(deps, workspace, "fake")
    collected: list[object] = []
    original = controller.dispatch

    def wrapped(action):  # type: ignore[no-untyped-def]
        for item in original(action):
            collected.append(item)
            yield item

    controller.dispatch = wrapped  # type: ignore[method-assign]
    io = ScriptedIO(["/help", "/doctor", "/exit"])
    driver = PlainSessionDriver(deps, workspace, "fake", io, controller=controller)
    assert driver.run() == 0
    rendered = "\n".join(io.output)
    assert "/doctor" in rendered
    assert "version" in rendered
    assert "pass" in rendered
    assert any(getattr(item, "type", "") == "session.help" for item in collected)
    assert any(getattr(item, "type", "") == "session.doctor" for item in collected)

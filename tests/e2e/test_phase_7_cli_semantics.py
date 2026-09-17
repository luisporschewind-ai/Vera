from io import StringIO
from json import loads
from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_json_session import JsonSessionDriver
from vera.cli_plain_session import PlainSessionDriver
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import CloseSession, SubmitPrompt
from vera.session.controller import SessionController
from vera.session.protocol import encode_action
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


def _deps(tmp_path: Path, name: str) -> tuple[RuntimeDependencies, Path]:
    workspace = tmp_path / f"{name}-ws"
    workspace.mkdir()
    state_dir = tmp_path / f"{name}-state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    runtime = VeraRuntime(
        FakeModelAdapter([ModelTurn(assistant_text="ok", finish_reason="stop")]),
        ToolRegistry(),
        state_dir,
    )
    return RuntimeDependencies(runtime=runtime, config=config), workspace


def test_controller_plain_json_share_event_types_and_exit(tmp_path: Path) -> None:
    controller_deps, controller_ws = _deps(tmp_path, "ctl")
    controller = SessionController(controller_deps, controller_ws, "fake")
    controller_types = [
        item.type
        for action in (SubmitPrompt(text="hi"), CloseSession())
        for item in controller.dispatch(action)
        if isinstance(item, EventEnvelope)
    ]

    json_deps, json_ws = _deps(tmp_path, "json")
    json_driver = JsonSessionDriver(json_deps, json_ws, "fake")
    target = StringIO()
    source = StringIO(
        encode_action(SubmitPrompt(text="hi")) + "\n" + encode_action(CloseSession()) + "\n"
    )
    json_code = json_driver.run(source, target)
    json_types = [
        item["event"]["type"]
        for line in target.getvalue().splitlines()
        if (item := loads(line)).get("event")
    ]

    plain_deps, plain_ws = _deps(tmp_path, "plain")
    io = ScriptedIO(["hi", "/exit"])
    plain_code = PlainSessionDriver(plain_deps, plain_ws, "fake", io).run()

    assert "run.completed" in controller_types
    assert "run.completed" in json_types
    assert "approval.required" not in controller_types
    assert "approval.required" not in json_types
    assert json_code == 0
    assert plain_code == 0
    assert "\u001b" not in target.getvalue()
    dumped = target.getvalue()
    assert '"reasoning"' in dumped or "run.completed" in dumped

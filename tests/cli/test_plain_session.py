from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_plain_session import PlainSessionDriver
from vera.cli_session import InteractiveSession
from vera.config import Limits, VeraConfig
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

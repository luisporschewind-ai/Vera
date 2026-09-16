import os
import sys
from pathlib import Path

from tests.pty.harness import PtyHarness
from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import ExecuteSlashCommand
from vera.session.controller import SessionController
from vera.tools.registry import ToolRegistry


def test_instructions_and_plain_start_hide_body(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = "SECRET_GUIDANCE_BODY_TOKEN"
    (workspace / "AGENTS.md").write_text(f"{secret}\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    runtime = VeraRuntime(
        FakeModelAdapter([ModelTurn(assistant_text="ok", finish_reason="stop")]),
        ToolRegistry(),
        state_dir,
    )
    controller = SessionController(
        RuntimeDependencies(
            runtime=runtime,
            config=VeraConfig(
                state_dir=state_dir,
                limits=Limits(),
                providers={
                    "fake": ProviderConfig(
                        base_url="https://example.invalid",
                        model="fake",
                        api_key_env="FAKE_API_KEY",
                    )
                },
            ),
            project_instructions=runtime.project_instructions,
        ),
        workspace,
        "fake",
    )
    outputs = list(controller.dispatch(ExecuteSlashCommand(raw="/instructions")))
    dumped = "".join(str(item.payload) for item in outputs)
    assert secret not in dumped
    assert any(item.type == "project.instructions.status" for item in outputs)


def test_pty_plain_start_does_not_write_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    before = sorted(path.name for path in workspace.iterdir())
    (tmp_path / "home").mkdir()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path / "home"),
        "TERM": "xterm-256color",
        "COLUMNS": "60",
        "LINES": "16",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        "VERA_PROVIDER_ENV_FILE": str(tmp_path / "missing.env"),
    }
    result = PtyHarness().spawn_and_run(
        [
            sys.executable,
            "-c",
            "from vera.cli import app; app()",
            "--plain",
            "--workspace",
            str(workspace),
        ],
        env=env,
        input_text="/exit\n",
        timeout=8.0,
    )
    after = sorted(path.name for path in workspace.iterdir())
    assert after == before
    assert (workspace / "VERA.md").exists() is False
    del result

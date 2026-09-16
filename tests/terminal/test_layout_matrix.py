from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.tools.registry import ToolRegistry


def make_app(tmp_path: Path) -> VeraTerminalApp:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = tmp_path / "state"
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
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir)
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    return VeraTerminalApp(controller, workspace, "fake", animations=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(60, 16), (80, 24), (120, 40)])
async def test_layout_matrix_keeps_composer_and_cjk_visible(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        composer = app.query_one("#composer")
        composer.load_text("你好 Vera café 👩‍💻 e\u0301")
        await pilot.pause()
        assert "你好" in composer.text
        assert "café" in composer.text
        assert "👩" in composer.text or "👩‍💻" in composer.text
        assert app.query_one("#timeline")
        assert app.query_one("#header")
        assert app.query_one("#welcome")
        assert app.query_one("#status-line")
        assert "VERA" in str(app.query_one("#header").render())
        assert app.query_one("#terminal-too-small").display is False
        if size[0] < 80:
            assert app.query_one("#welcome").display is False
            assert "\n" not in str(app.query_one("#header").render())
        else:
            assert app.query_one("#welcome").display is True
            assert "\n" in str(app.query_one("#header").render())

"""Phase 9 PTY dimensions for the plain client."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.pty.harness import PtyHarness
from tests.skills.test_manifest import write_skill


@pytest.mark.parametrize("columns,rows", [(60, 16), (80, 24)])
def test_phase_9_skills_plain_pty_is_readable_at_supported_sizes(
    tmp_path: Path, columns: int, rows: int
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_skill(workspace / ".vera" / "skills", name="pty-review")
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "TERM": "xterm-256color",
        "COLUMNS": str(columns),
        "LINES": str(rows),
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        "VERA_PROVIDER_ENV_FILE": str(tmp_path / "missing-provider.env"),
        "DEEPSEEK_API_KEY": "phase9-placeholder",
        "VERA_DEEPSEEK_BASE_URL": "https://example.invalid/v1",
        "VERA_DEEPSEEK_MODEL": "fake-model",
        "VERA_STATE_DIR": str(tmp_path / "state"),
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
        input_text=(
            "/skills\n/skills show pty-review\n/skills use pty-review\n/status\n"
            "/skills clear\n/exit\n"
        ),
        timeout=8.0,
    )

    assert result.exit_code == 0
    assert "pty-review" in result.output
    assert "# Skill" not in result.output
    assert "\x1b" not in result.output

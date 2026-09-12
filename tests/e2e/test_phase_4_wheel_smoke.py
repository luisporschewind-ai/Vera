from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class InstalledVera:
    vera: Path
    env: dict[str, str]
    home: Path

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.vera), *args],
            cwd=self.home,
            env=self.env,
            check=False,
            capture_output=True,
            text=True,
        )


def _build_wheel(dist: Path) -> Path:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/vera-uv-cache")
    proc = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    wheels = list(dist.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _isolated_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_STATE_HOME"] = str(home / "state")
    env["XDG_CONFIG_HOME"] = str(home / "config")
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    for key in list(env):
        upper = key.upper()
        if (
            upper.startswith(
                ("DEEPSEEK_", "GLM_", "VERA_LIVE_", "VERA_DEEPSEEK_", "VERA_GLM_", "OPENAI_")
            )
            or upper == "VERA_PROVIDER_ENV_FILE"
        ):
            env.pop(key)
    env["VERA_PROVIDER_ENV_FILE"] = str(home / "missing-provider.env")
    return env


@pytest.fixture(scope="module")
def installed_vera(tmp_path_factory: pytest.TempPathFactory) -> InstalledVera:
    root = tmp_path_factory.mktemp("wheel-smoke")
    wheel = _build_wheel(root / "dist")
    venv_dir = root / "venv"
    home = root / "home"
    home.mkdir()
    env = _isolated_env(home)
    env.setdefault("UV_CACHE_DIR", "/private/tmp/vera-uv-cache")
    created = subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(venv_dir)],
        cwd=home,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    python = venv_dir / "bin" / "python"
    install = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "--offline", str(wheel)],
        cwd=home,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stderr
    vera = venv_dir / "bin" / "vera"
    assert vera.is_file()
    return InstalledVera(vera=vera, env=env, home=home)


def test_built_wheel_contains_runnable_corpus(installed_vera: InstalledVera) -> None:
    listed = installed_vera.run("eval", "list", "--json")
    assert listed.returncode == 0, listed.stderr
    payload = json.loads(listed.stdout)
    assert len(payload["cases"]) == 14
    run = installed_vera.run("eval", "run", "plain-answer", "--json")
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["case_id"] == "plain-answer"
    assert report["status"] == "pass"
    leftover, index = json.JSONDecoder().raw_decode(run.stdout.strip())
    del leftover
    assert run.stdout.strip()[index:].strip() == ""

#!/usr/bin/env python3
"""Install a local Vera wheel in an isolated venv and smoke it outside the repo."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from smoke_support.cli_checks import run_cli_checks, with_placeholder_provider
from smoke_support.core_payload import _CORE_SMOKE
from smoke_support.session_checks import run_instruction_checks, run_session_checks

from vera.evals.corpus import sha256_tree


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
    )


def _find_wheel(dist: Path) -> Path:
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        raise SystemExit(f"no wheel in {dist}")
    return wheels[-1]


def _isolated_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_STATE_HOME"] = str(home / "xdg-state")
    env["XDG_CONFIG_HOME"] = str(home / "xdg-config")
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/private/tmp/vera-uv-cache")
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
    env.pop("PYTHONPATH", None)
    return env


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--venv", type=Path, default=None)
    parser.add_argument("--wheel", type=Path, default=None)
    args = parser.parse_args(argv)
    dist = args.dist.resolve()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    venv = (args.venv or (dist / "venv")).resolve()
    wheel = (args.wheel or _find_wheel(dist)).resolve()
    home = dist / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = _isolated_env(home)
    state_dir = home / "vera-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    env["VERA_STATE_DIR"] = str(state_dir)
    before = sha256_tree(workspace)

    created = _run(
        ["uv", "venv", "--python", sys.executable, str(venv)],
        cwd=workspace,
        env=env,
    )
    if created.returncode != 0:
        sys.stderr.write(created.stderr)
        return created.returncode or 1
    python = venv / "bin" / "python"
    vera = venv / "bin" / "vera"
    install = _run(
        ["uv", "pip", "install", "--python", str(python), "--offline", str(wheel)],
        cwd=workspace,
        env=env,
    )
    if install.returncode != 0:
        sys.stderr.write(install.stderr)
        return install.returncode or 1
    core_smoke = _run(
        [str(python), "-c", _CORE_SMOKE, str(dist / "installed-core-smoke")],
        cwd=workspace,
        env=env,
    )
    if core_smoke.returncode != 0:
        sys.stderr.write(core_smoke.stdout + core_smoke.stderr)
        return core_smoke.returncode or 1
    repeat = _run(
        ["uv", "pip", "install", "--python", str(python), "--offline", str(wheel)],
        cwd=workspace,
        env=env,
    )
    if repeat.returncode != 0:
        sys.stderr.write(repeat.stderr)
        return repeat.returncode or 1

    ready = with_placeholder_provider(env)
    code = run_cli_checks(vera, workspace=workspace, env=env, ready=ready, run=_run)
    if code:
        return code
    code = run_session_checks(
        vera,
        workspace=workspace,
        env=env,
        ready=ready,
        state_dir=state_dir,
        home=home,
        run=_run,
    )
    if code:
        return code
    if sha256_tree(workspace) != before:
        sys.stderr.write("workspace hash changed during wheel smoke\n")
        return 1
    return run_instruction_checks(
        vera,
        workspace=workspace,
        env=env,
        ready=ready,
        home=home,
        workspace_before=before,
        run=_run,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

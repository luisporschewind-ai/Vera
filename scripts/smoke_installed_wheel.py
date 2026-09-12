#!/usr/bin/env python3
"""Install a local Vera wheel in an isolated venv and smoke it outside the repo."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from vera.evals.corpus import sha256_tree

CLOSE_SESSION = '{"schema_version":1,"type":"session.close"}\n'
PLACEHOLDER_KEY = "vera-test-placeholder-not-a-secret"


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
    return env


def _with_placeholder_provider(env: dict[str, str]) -> dict[str, str]:
    updated = env.copy()
    updated["DEEPSEEK_API_KEY"] = PLACEHOLDER_KEY
    updated["VERA_DEEPSEEK_BASE_URL"] = "https://example.invalid/v1"
    updated["VERA_DEEPSEEK_MODEL"] = "fake-model"
    return updated


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
    repeat = _run(
        ["uv", "pip", "install", "--python", str(python), "--offline", str(wheel)],
        cwd=workspace,
        env=env,
    )
    if repeat.returncode != 0:
        sys.stderr.write(repeat.stderr)
        return repeat.returncode or 1

    help_proc = _run([str(vera), "--help"], cwd=workspace, env=env)
    if help_proc.returncode != 0 or (
        "Usage" not in help_proc.stdout and "usage" not in help_proc.stdout
    ):
        sys.stderr.write(help_proc.stdout + help_proc.stderr)
        return help_proc.returncode or 1

    for args_cli in (["eval", "validate", "--json"], ["eval", "list", "--json"]):
        proc = _run([str(vera), *args_cli], cwd=workspace, env=env)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            return proc.returncode or 1
        payload = json.loads(proc.stdout)
        if payload.get("schema_version") != 1:
            sys.stderr.write("eval json schema_version mismatch\n")
            return 1

    missing = _run([str(vera), "--plain"], cwd=workspace, env=env, input_text="/exit\n")
    missing_text = missing.stderr + missing.stdout
    if missing.returncode != 5 or "missing_provider_config" not in missing_text:
        sys.stderr.write(missing.stdout + missing.stderr)
        return missing.returncode or 1

    ready = _with_placeholder_provider(env)
    default_mode = _run([str(vera)], cwd=workspace, env=ready)
    if default_mode.returncode != 2:
        sys.stderr.write(default_mode.stdout + default_mode.stderr)
        return default_mode.returncode or 1

    json_session = _run(
        [str(vera), "--json"],
        cwd=workspace,
        env=ready,
        input_text=CLOSE_SESSION,
    )
    if json_session.returncode != 0:
        sys.stderr.write(json_session.stderr)
        return json_session.returncode or 1

    plain = _run([str(vera), "--plain"], cwd=workspace, env=ready, input_text="/exit\n")
    if plain.returncode != 0:
        sys.stderr.write(plain.stderr)
        return plain.returncode or 1

    blocked_parent = home / "blocked-parent"
    blocked_parent.mkdir(parents=True, exist_ok=True)
    blocked_parent.chmod(0o500)
    blocked_env = ready.copy()
    blocked_env["VERA_STATE_DIR"] = str(blocked_parent / "vera-state")
    unwritable = _run([str(vera), "--plain"], cwd=workspace, env=blocked_env, input_text="/exit\n")
    blocked_parent.chmod(0o700)
    if unwritable.returncode != 5 or "state_unwritable" not in (
        unwritable.stderr + unwritable.stdout
    ):
        sys.stderr.write(unwritable.stdout + unwritable.stderr)
        return unwritable.returncode or 1

    future_home = home / "future-state"
    future_run = future_home / "runs" / "run_future"
    future_run.mkdir(parents=True, exist_ok=True)
    manifest = (
        '{"manifest_version":99,"journal_format_version":1,"run_id":"run_future",'
        '"created_at":"2026-09-11T00:00:00Z"}'
    )
    (future_run / "manifest.json").write_text(manifest, encoding="utf-8")
    (future_run / "events.jsonl").write_text("", encoding="utf-8")
    future_env = ready.copy()
    future_env["VERA_STATE_DIR"] = str(future_home)
    inspected = _run(
        [str(vera), "state", "inspect", "run_future", "--json"],
        cwd=workspace,
        env=future_env,
    )
    if inspected.returncode != 0:
        sys.stderr.write(inspected.stderr)
        return inspected.returncode or 1
    record = json.loads(inspected.stdout.strip().splitlines()[-1])
    if record.get("payload", {}).get("format_status") != "unsupported":
        sys.stderr.write(inspected.stdout)
        return 1
    if (future_run / "manifest.json").read_text(encoding="utf-8") != manifest:
        sys.stderr.write("unknown schema overwritten\n")
        return 1

    after = sha256_tree(workspace)
    if after != before:
        sys.stderr.write("workspace hash changed during wheel smoke\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

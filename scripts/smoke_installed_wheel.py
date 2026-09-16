#!/usr/bin/env python3
"""Install a local Vera wheel in an isolated venv and smoke it outside the repo."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from vera.evals.corpus import sha256_tree

CLOSE_SESSION = '{"schema_version":1,"type":"session.close"}\n'
PLACEHOLDER_KEY = "vera-test-placeholder-not-a-secret"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


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
    help_text = _ANSI.sub("", help_proc.stdout)
    help_ok = help_proc.returncode == 0 and ("Usage" in help_text or "usage" in help_text)
    if not help_ok or "--version" not in help_text:
        sys.stderr.write(help_proc.stdout + help_proc.stderr)
        return help_proc.returncode or 1

    version_proc = _run([str(vera), "--version"], cwd=workspace, env=env)
    if version_proc.returncode != 0 or "vera 0.1.0" not in version_proc.stdout:
        sys.stderr.write(version_proc.stdout + version_proc.stderr)
        return version_proc.returncode or 1
    json_version = _run([str(vera), "--json", "--version"], cwd=workspace, env=env)
    if json_version.returncode != 0:
        sys.stderr.write(json_version.stdout + json_version.stderr)
        return json_version.returncode or 1
    version_payload = json.loads(json_version.stdout)
    if (
        version_payload.get("name") != "vera"
        or version_payload.get("version") != "0.1.0"
        or version_payload.get("install") != "wheel"
        or "site-packages" not in str(version_payload.get("location", ""))
        or "git" in version_payload
    ):
        sys.stderr.write(json_version.stdout)
        return 1

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

    no_continue = _run([str(vera), "--json", "-c"], cwd=workspace, env=ready)
    if no_continue.returncode != 2:
        sys.stderr.write(no_continue.stdout + no_continue.stderr)
        return no_continue.returncode or 1
    if "\u001b" in no_continue.stdout:
        sys.stderr.write("continue json emitted ANSI\n")
        return 1

    json_session = _run(
        [str(vera), "--json"],
        cwd=workspace,
        env=ready,
        input_text=CLOSE_SESSION,
    )
    if json_session.returncode != 0:
        sys.stderr.write(json_session.stderr)
        return json_session.returncode or 1

    picker = _run(
        [str(vera), "--json", "-r"],
        cwd=workspace,
        env=ready,
        input_text="should-not-be-id\n",
    )
    if picker.returncode != 2 or "\u001b" in picker.stdout:
        sys.stderr.write(picker.stdout + picker.stderr)
        return picker.returncode or 1

    missing_resume = _run(
        [str(vera), "--json", "-r", "session_missing"],
        cwd=workspace,
        env=ready,
    )
    if missing_resume.returncode != 2:
        sys.stderr.write(missing_resume.stdout + missing_resume.stderr)
        return missing_resume.returncode or 1

    listed = _run(
        [str(vera), "--json"],
        cwd=workspace,
        env=ready,
        input_text='{"schema_version":1,"type":"session.command","raw":"/sessions"}\n'
        + CLOSE_SESSION,
    )
    if listed.returncode != 0:
        sys.stderr.write(listed.stderr)
        return listed.returncode or 1
    if not any(
        (json.loads(line).get("event") or {}).get("type") == "session.listed"
        for line in listed.stdout.splitlines()
        if line.strip()
    ):
        sys.stderr.write(listed.stdout)
        return 1

    doctor_input = '{"schema_version":1,"type":"session.command","raw":"/doctor"}\n' + CLOSE_SESSION
    doctor = _run([str(vera), "--json"], cwd=workspace, env=ready, input_text=doctor_input)
    if doctor.returncode != 0:
        sys.stderr.write(doctor.stderr)
        return doctor.returncode or 1
    doctor_types = []
    for line in doctor.stdout.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        event = record.get("event") or {}
        doctor_types.append(event.get("type"))
        if event.get("type") == "session.doctor":
            names = [item.get("name") for item in event.get("payload", {}).get("items", [])]
            if names != ["version", "python", "terminal", "config", "state_dir", "git"]:
                sys.stderr.write(doctor.stdout)
                return 1
    if "session.doctor" not in doctor_types or "\u001b" in doctor.stdout:
        sys.stderr.write(doctor.stdout + doctor.stderr)
        return 1

    run_missing = _run([str(vera), "run", "hello"], cwd=workspace, env=env)
    if run_missing.returncode != 5 or "missing_provider_config" not in (
        run_missing.stderr + run_missing.stdout
    ):
        sys.stderr.write(run_missing.stdout + run_missing.stderr)
        return run_missing.returncode or 1

    plain = _run(
        [str(vera), "--plain"],
        cwd=workspace,
        env=ready,
        input_text="/doctor\n/exit\n",
    )
    if plain.returncode != 0 or "version" not in (plain.stdout + plain.stderr):
        sys.stderr.write(plain.stdout + plain.stderr)
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

    extra = home / "instruction-workspace"
    extra.mkdir(parents=True)
    (extra / "AGENTS.md").write_text("agents base\n", encoding="utf-8")
    (extra / "VERA.md").write_text("vera extra\n", encoding="utf-8")
    snap = sha256_tree(extra)
    instruction_input = (
        '{"schema_version":1,"type":"session.command","raw":"/instructions"}\n' + CLOSE_SESSION
    )
    instructions = _run(
        [str(vera), "--workspace", str(extra), "--json"],
        cwd=extra,
        env=ready,
        input_text=instruction_input,
    )
    if instructions.returncode != 0:
        sys.stderr.write(instructions.stdout + instructions.stderr)
        return instructions.returncode or 1
    if "agents base" in instructions.stdout or "vera extra" in instructions.stdout:
        sys.stderr.write("project instruction body leaked\n")
        return 1
    status_types = []
    for line in instructions.stdout.splitlines():
        if not line.strip():
            continue
        event = json.loads(line).get("event") or {}
        status_types.append(event.get("type"))
    if "project.instructions.status" not in status_types:
        sys.stderr.write("missing project.instructions.status\n")
        sys.stderr.write(instructions.stdout)
        return 1
    init_help = _run([str(vera), "init", "--help"], cwd=extra, env=env)
    if init_help.returncode != 0 or "只提议 VERA.md" not in _ANSI.sub("", init_help.stdout):
        sys.stderr.write(init_help.stdout + init_help.stderr)
        return init_help.returncode or 1
    init_json = _run(
        [str(vera), "init", "--workspace", str(extra), "--json"],
        cwd=extra,
        env=ready,
    )
    if sha256_tree(extra) != snap:
        sys.stderr.write("vera init wrote the workspace without approval\n")
        return 1
    if "agents base" in init_json.stdout:
        sys.stderr.write("init output leaked project instruction body\n")
        return 1
    if sha256_tree(workspace) != before:
        sys.stderr.write("instruction smoke mutated the primary workspace\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

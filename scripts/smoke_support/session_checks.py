"""Installed-wheel session, recovery and instruction checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from vera.evals.corpus import sha256_tree

CLOSE_SESSION = '{"schema_version":1,"type":"session.close"}\n'
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def run_session_checks(
    vera: Path,
    *,
    workspace: Path,
    env: dict[str, str],
    ready: dict[str, str],
    state_dir: Path,
    home: Path,
    run: Runner,
) -> int:
    json_session = run(
        [str(vera), "--json"],
        cwd=workspace,
        env=ready,
        input_text=CLOSE_SESSION,
    )
    if json_session.returncode != 0:
        sys.stderr.write(json_session.stderr)
        return json_session.returncode or 1

    picker = run(
        [str(vera), "--json", "-r"],
        cwd=workspace,
        env=ready,
        input_text="should-not-be-id\n",
    )
    if picker.returncode != 2 or "\u001b" in picker.stdout:
        sys.stderr.write(picker.stdout + picker.stderr)
        return picker.returncode or 1

    missing_resume = run(
        [str(vera), "--json", "-r", "session_missing"],
        cwd=workspace,
        env=ready,
    )
    if missing_resume.returncode != 2:
        sys.stderr.write(missing_resume.stdout + missing_resume.stderr)
        return missing_resume.returncode or 1

    listed = run(
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

    session_dirs = [path for path in (state_dir / "sessions").iterdir() if path.is_dir()]
    if not session_dirs:
        sys.stderr.write("json session did not create VERA_STATE_DIR sessions\n")
        return 1
    session_id = session_dirs[0].name
    journal_path = session_dirs[0] / "session.jsonl"
    v1_bytes = journal_path.read_bytes()
    if b'"session_format_version":1' not in v1_bytes.replace(b" ", b""):
        sys.stderr.write("created session journal is not v1\n")
        return 1

    continued = run(
        [str(vera), "--json", "-c"],
        cwd=workspace,
        env=ready,
        input_text=CLOSE_SESSION,
    )
    if continued.returncode != 0 or "\u001b" in continued.stdout:
        sys.stderr.write(continued.stdout + continued.stderr)
        return continued.returncode or 1
    if "session.loaded" not in continued.stdout:
        sys.stderr.write("continue did not emit session.loaded\n")
        sys.stderr.write(continued.stdout)
        return 1

    healthy = run(
        [
            str(vera),
            "sessions",
            "inspect",
            session_id,
            "--workspace",
            str(workspace),
            "--json",
        ],
        cwd=workspace,
        env=ready,
    )
    if healthy.returncode != 2:
        sys.stderr.write(healthy.stdout + healthy.stderr)
        return healthy.returncode or 1

    journal_path.write_bytes(v1_bytes + b'{"session_format_version":1')
    inspect_trunc = run(
        [
            str(vera),
            "sessions",
            "inspect",
            session_id,
            "--workspace",
            str(workspace),
            "--json",
        ],
        cwd=workspace,
        env=ready,
    )
    if inspect_trunc.returncode != 0:
        sys.stderr.write(inspect_trunc.stdout + inspect_trunc.stderr)
        return inspect_trunc.returncode or 1
    inspect_payload = json.loads(inspect_trunc.stdout.strip().splitlines()[-1])
    if inspect_payload.get("failure_code") != "truncated_tail":
        sys.stderr.write(inspect_trunc.stdout)
        return 1
    repair = run(
        [
            str(vera),
            "sessions",
            "repair",
            session_id,
            "--workspace",
            str(workspace),
            "--json",
        ],
        cwd=workspace,
        env=ready,
    )
    if repair.returncode != 0:
        sys.stderr.write(repair.stdout + repair.stderr)
        return repair.returncode or 1
    repair_payload = json.loads(repair.stdout.strip().splitlines()[-1])
    if repair_payload.get("applied") is not False:
        sys.stderr.write(repair.stdout)
        return 1
    truncated = v1_bytes + b'{"session_format_version":1'
    if journal_path.read_bytes() != truncated:
        sys.stderr.write("repair dry-run mutated session journal\n")
        return 1
    journal_path.write_bytes(v1_bytes)

    relisted = run(
        [str(vera), "--json"],
        cwd=workspace,
        env=ready,
        input_text='{"schema_version":1,"type":"session.command","raw":"/sessions"}\n'
        + CLOSE_SESSION,
    )
    if relisted.returncode != 0:
        sys.stderr.write(relisted.stderr)
        return relisted.returncode or 1
    listed_ids: list[str] = []
    for line in relisted.stdout.splitlines():
        if not line.strip():
            continue
        event = json.loads(line).get("event") or {}
        if event.get("type") == "session.listed":
            listed_ids = [
                str(item.get("session_id")) for item in event.get("payload", {}).get("items", [])
            ]
    if session_id not in listed_ids:
        sys.stderr.write("v1 session disappeared from rebuilt list\n")
        sys.stderr.write(relisted.stdout)
        return 1

    doctor_input = '{"schema_version":1,"type":"session.command","raw":"/doctor"}\n' + CLOSE_SESSION
    doctor = run([str(vera), "--json"], cwd=workspace, env=ready, input_text=doctor_input)
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

    run_missing = run([str(vera), "run", "hello"], cwd=workspace, env=env)
    if run_missing.returncode != 5 or "missing_provider_config" not in (
        run_missing.stderr + run_missing.stdout
    ):
        sys.stderr.write(run_missing.stdout + run_missing.stderr)
        return run_missing.returncode or 1

    plain = run(
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
    unwritable = run([str(vera), "--plain"], cwd=workspace, env=blocked_env, input_text="/exit\n")
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
    inspected = run(
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
    return 0


def run_instruction_checks(
    vera: Path,
    *,
    workspace: Path,
    env: dict[str, str],
    ready: dict[str, str],
    home: Path,
    workspace_before: str,
    run: Runner,
) -> int:
    extra = home / "instruction-workspace"
    extra.mkdir(parents=True)
    (extra / "AGENTS.md").write_text("agents base\n", encoding="utf-8")
    (extra / "VERA.md").write_text("vera extra\n", encoding="utf-8")
    snap = sha256_tree(extra)
    instruction_input = (
        '{"schema_version":1,"type":"session.command","raw":"/instructions"}\n' + CLOSE_SESSION
    )
    instructions = run(
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
    init_help = run([str(vera), "init", "--help"], cwd=extra, env=env)
    if init_help.returncode != 0 or "只提议 VERA.md" not in _ANSI.sub("", init_help.stdout):
        sys.stderr.write(init_help.stdout + init_help.stderr)
        return init_help.returncode or 1
    init_json = run(
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
    if sha256_tree(workspace) != workspace_before:
        sys.stderr.write("instruction smoke mutated the primary workspace\n")
        return 1
    return 0

"""Installed-wheel CLI and provider configuration checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

PLACEHOLDER_KEY = "vera-test-placeholder-not-a-secret"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def with_placeholder_provider(env: dict[str, str]) -> dict[str, str]:
    updated = env.copy()
    updated["DEEPSEEK_API_KEY"] = PLACEHOLDER_KEY
    updated["VERA_DEEPSEEK_BASE_URL"] = "https://example.invalid/v1"
    updated["VERA_DEEPSEEK_MODEL"] = "fake-model"
    return updated


def run_cli_checks(
    vera: Path,
    *,
    workspace: Path,
    env: dict[str, str],
    ready: dict[str, str],
    run: Runner,
) -> int:
    help_proc = run([str(vera), "--help"], cwd=workspace, env=env)
    help_text = _ANSI.sub("", help_proc.stdout)
    help_ok = help_proc.returncode == 0 and ("Usage" in help_text or "usage" in help_text)
    if not help_ok or "--version" not in help_text:
        sys.stderr.write(help_proc.stdout + help_proc.stderr)
        return help_proc.returncode or 1

    version_proc = run([str(vera), "--version"], cwd=workspace, env=env)
    if version_proc.returncode != 0 or "vera 0.1.0" not in version_proc.stdout:
        sys.stderr.write(version_proc.stdout + version_proc.stderr)
        return version_proc.returncode or 1
    json_version = run([str(vera), "--json", "--version"], cwd=workspace, env=env)
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
        proc = run([str(vera), *args_cli], cwd=workspace, env=env)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            return proc.returncode or 1
        payload = json.loads(proc.stdout)
        if payload.get("schema_version") != 1:
            sys.stderr.write("eval json schema_version mismatch\n")
            return 1

    missing = run([str(vera), "--plain"], cwd=workspace, env=env, input_text="/exit\n")
    missing_text = missing.stderr + missing.stdout
    if missing.returncode != 5 or "missing_provider_config" not in missing_text:
        sys.stderr.write(missing.stdout + missing.stderr)
        return missing.returncode or 1

    # The caller supplies the provider-ready environment.
    default_mode = run([str(vera)], cwd=workspace, env=ready)
    if default_mode.returncode != 2:
        sys.stderr.write(default_mode.stdout + default_mode.stderr)
        return default_mode.returncode or 1

    no_continue = run([str(vera), "--json", "-c"], cwd=workspace, env=ready)
    if no_continue.returncode != 2:
        sys.stderr.write(no_continue.stdout + no_continue.stderr)
        return no_continue.returncode or 1
    if "\u001b" in no_continue.stdout:
        sys.stderr.write("continue json emitted ANSI\n")
        return 1

    return 0

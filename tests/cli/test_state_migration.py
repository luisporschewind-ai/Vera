"""CLI state inspect/migrate command tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.config import Limits, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_state_inspect_and_migrate_json(tmp_path: Path, monkeypatch) -> None:
    source = Path(__file__).resolve().parents[1] / "fixtures" / "state" / "legacy-v1" / "run_legacy"
    state = tmp_path / "state"
    target = state / "runs" / "run_legacy"
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        state,
        installation_id="install-1",
    )
    deps = RuntimeDependencies(
        runtime=runtime,
        config=VeraConfig(state_dir=state, limits=Limits(), providers={}),
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *args, **kwargs: deps)
    monkeypatch.setattr("vera.cli.load_config", lambda *args, **kwargs: deps.config)

    runner = CliRunner()
    inspected = runner.invoke(app, ["state", "inspect", "--json"])
    assert inspected.exit_code == 0
    payload = json.loads(inspected.stdout.strip().splitlines()[-1])
    assert payload["type"] == "state.inspected"
    assert payload["payload"]["format_status"] == "legacy"

    dry = runner.invoke(app, ["state", "migrate", "run_legacy", "--json"])
    assert dry.exit_code == 0
    planned = json.loads(dry.stdout.strip().splitlines()[-1])
    assert planned["type"] == "state.migration_planned"

    applied = runner.invoke(
        app,
        [
            "state",
            "migrate",
            "run_legacy",
            "--apply",
            "--migration-hash",
            planned["payload"]["migration_hash"],
            "--migration-id",
            planned["payload"]["migration_id"],
            "--json",
        ],
    )
    assert applied.exit_code == 0
    completed = json.loads(applied.stdout.strip().splitlines()[-1])
    assert completed["type"] == "state.migration_completed"

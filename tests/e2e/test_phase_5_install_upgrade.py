"""Warehouse-out wheel install, upgrade, and fail-closed configuration."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vera.evals.corpus import sha256_tree
from vera.persistence.errors import StateVersionError
from vera.persistence.journal_codec import CURRENT_JOURNAL_FORMAT_VERSION
from vera.persistence.migration import StateMigrationService
from vera.persistence.run_store import RunFormatStatus, RunStore
from vera.persistence.snapshot_codec import CURRENT_SNAPSHOT_VERSION, SnapshotCodec

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_RUN = REPO_ROOT / "tests" / "fixtures" / "state" / "legacy-v1" / "run_legacy"
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke_installed_wheel.py"


def _copy_legacy(state: Path, run_id: str = "run_legacy") -> Path:
    target = state / "runs" / run_id
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(LEGACY_RUN, target)
    return target


def test_sha256_tree_is_stable_for_copied_fixture(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "projects" / "python-minimal", first)
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "projects" / "python-minimal", second)
    assert sha256_tree(first) == sha256_tree(second)
    (first / "src" / "demo" / "__init__.py").write_text("changed\n", encoding="utf-8")
    assert sha256_tree(first) != sha256_tree(second)


def test_legacy_migration_is_idempotent_and_preserves_journal(tmp_path: Path) -> None:
    state = tmp_path / "state"
    run_dir = _copy_legacy(state)
    events_before = (run_dir / "events.jsonl").read_bytes()
    service = StateMigrationService(state)
    first = service.apply(service.plan("run_legacy"))
    assert first.status == "completed"
    assert (run_dir / "events.jsonl").read_bytes() == events_before
    assert RunStore(state).format_status("run_legacy") is RunFormatStatus.CURRENT
    second = service.apply(service.plan("run_legacy"))
    assert second.status == "noop"
    assert (run_dir / "events.jsonl").read_bytes() == events_before
    assert RunStore(state).format_status("run_legacy") is RunFormatStatus.CURRENT


def test_unknown_and_corrupt_state_keep_original_bytes(tmp_path: Path) -> None:
    state = tmp_path / "state"
    future = state / "runs" / "run_future"
    future.mkdir(parents=True)
    manifest = (
        '{"manifest_version":99,"journal_format_version":1,"run_id":"run_future",'
        '"created_at":"2026-09-11T00:00:00Z"}'
    )
    (future / "manifest.json").write_text(manifest, encoding="utf-8")
    (future / "events.jsonl").write_bytes(b"")
    assert RunStore(state).format_status("run_future") is RunFormatStatus.UNSUPPORTED
    assert (future / "manifest.json").read_text(encoding="utf-8") == manifest

    corrupt = state / "runs" / "run_corrupt"
    corrupt.mkdir()
    payload = b"{broken\n"
    (corrupt / "events.jsonl").write_bytes(payload)
    assert RunStore(state).format_status("run_corrupt") is RunFormatStatus.CORRUPT
    assert (corrupt / "events.jsonl").read_bytes() == payload

    with pytest.raises(StateVersionError, match="unsupported_version"):
        SnapshotCodec().decode('{"snapshot_version":99,"run_id":"run_x"}')
    assert CURRENT_JOURNAL_FORMAT_VERSION == 1
    assert CURRENT_SNAPSHOT_VERSION == 1


def test_migration_write_failure_keeps_legacy_bytes(tmp_path: Path) -> None:
    state = tmp_path / "state"
    run_dir = _copy_legacy(state)
    before = (run_dir / "events.jsonl").read_bytes()
    service = StateMigrationService(state)
    plan = service.plan("run_legacy")

    def fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError("injected")

    result = service.apply(plan, replace=fail_replace)
    assert result.status == "failed"
    assert result.advice is not None
    assert (run_dir / "events.jsonl").read_bytes() == before
    assert RunStore(state).format_status("run_legacy") is RunFormatStatus.LEGACY


@pytest.fixture(scope="module")
def phase5_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dist = tmp_path_factory.mktemp("phase5-dist")
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/vera-uv-cache")
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert built.returncode == 0, built.stderr
    assert list(dist.glob("*.whl"))
    return dist


def test_smoke_installed_wheel_outside_repo(
    tmp_path_factory: pytest.TempPathFactory, phase5_dist: Path
) -> None:
    root = tmp_path_factory.mktemp("phase5-smoke")
    workspace = root / "workspace"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "projects" / "python-minimal", workspace)
    before = sha256_tree(workspace)
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/vera-uv-cache")
    for key in (
        "DEEPSEEK_API_KEY",
        "GLM_API_KEY",
        "VERA_LIVE_API_KEY",
        "VERA_PROVIDER_ENV_FILE",
    ):
        env.pop(key, None)
    proc = subprocess.run(
        [
            sys.executable,
            str(SMOKE_SCRIPT),
            "--dist",
            str(phase5_dist),
            "--workspace",
            str(workspace),
            "--venv",
            str(root / "venv"),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sha256_tree(workspace) == before

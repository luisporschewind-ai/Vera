from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_CASE_IDS = {
    "create-file",
    "update-file",
    "multi-file-edit",
    "plain-answer",
    "verification-passes",
    "reject-keeps-original",
    "path-escape-denied",
    "forbidden-command",
    "usage-null-safe",
    "rollback-after-apply",
    "resume-after-approval",
    "restore-partial-apply",
    "in-flight-manual",
    "idempotent-resume",
}


def _build(tmp_path: Path) -> tuple[Path, Path]:
    dist = tmp_path / "dist"
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/vera-uv-cache")
    proc = subprocess.run(
        ["uv", "build", "--out-dir", str(dist)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    assert len(wheels) == 1
    assert len(sdists) == 1
    return wheels[0], sdists[0]


def _case_ids_from_names(names: list[str], marker: str) -> set[str]:
    found: set[str] = set()
    for name in names:
        if marker not in name or not name.endswith("/case.json"):
            continue
        found.add(Path(name).parent.name)
    return found


@pytest.fixture(scope="module")
def built_artifacts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    return _build(tmp_path_factory.mktemp("dist-parent"))


def test_wheel_and_sdist_contain_frozen_corpus(built_artifacts: tuple[Path, Path]) -> None:
    wheel, sdist = built_artifacts
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
    assert "vera/evals/corpus/manifest.json" in wheel_names
    wheel_ids = _case_ids_from_names(wheel_names, "/evals/corpus/")
    assert wheel_ids == FROZEN_CASE_IDS

    with tarfile.open(sdist) as archive:
        sdist_names = [member.name for member in archive.getmembers() if member.isfile()]
    sdist_ids = _case_ids_from_names(sdist_names, "/evals/corpus/")
    assert sdist_ids == FROZEN_CASE_IDS
    assert any(name.endswith("/vera/evals/corpus/manifest.json") for name in sdist_names)


def test_extracted_wheel_discovers_fourteen_cases(
    tmp_path: Path, built_artifacts: tuple[Path, Path]
) -> None:
    wheel, _sdist = built_artifacts
    extracted = tmp_path / "wheel"
    extracted.mkdir()
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(extracted)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(extracted)
    for key in list(env):
        upper = key.upper()
        if upper.startswith(("DEEPSEEK_", "GLM_", "VERA_LIVE_", "OPENAI_")):
            env.pop(key)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from vera.evals.corpus import CorpusLoader;"
                "cases = CorpusLoader().list_cases();"
                "print(len(cases))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "14"

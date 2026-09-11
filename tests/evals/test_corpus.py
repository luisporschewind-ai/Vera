from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from vera.evals.contracts import EvalTag
from vera.evals.corpus import CorpusError, CorpusLoader

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "evals" / "valid"


def _copy_valid(tmp_path: Path) -> Path:
    dest = tmp_path / "corpus"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def _write_manifest(root: Path) -> None:
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == root / "manifest.json":
            continue
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": files}, indent=2) + "\n",
        encoding="utf-8",
    )


def test_loader_validates_manifest_and_returns_sorted_cases(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    loader = CorpusLoader(valid_corpus)
    result = loader.validate()
    assert result.case_ids == ("plain-answer",)
    assert result.file_count == 4
    loaded = loader.load("plain-answer")
    assert loaded.case.goal == "用一句话说明仓库用途"
    assert loaded.case.tags == (EvalTag.CONVERSATION,)
    assert loader.list_cases()[0].case_id == "plain-answer"


def test_loader_rejects_hash_mismatch(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    (valid_corpus / "plain-answer" / "case.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CorpusError, match="manifest_mismatch"):
        CorpusLoader(valid_corpus).validate()


def test_loader_rejects_unregistered_file(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    (valid_corpus / "plain-answer" / "extra.txt").write_text("nope\n", encoding="utf-8")
    with pytest.raises(CorpusError, match="unregistered_file"):
        CorpusLoader(valid_corpus).validate()


def test_loader_rejects_directory_name_mismatch(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    case_path = valid_corpus / "plain-answer" / "case.json"
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["case_id"] = "create-file"
    case_path.write_text(json.dumps(payload), encoding="utf-8")
    _write_manifest(valid_corpus)
    with pytest.raises(CorpusError, match="case_id_mismatch"):
        CorpusLoader(valid_corpus).validate()


def test_loader_rejects_symlink(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    target = valid_corpus / "plain-answer" / "workspace" / "README.md"
    link = valid_corpus / "plain-answer" / "workspace" / "link.md"
    link.symlink_to(target)
    _write_manifest(valid_corpus)
    with pytest.raises(CorpusError, match="special_file"):
        CorpusLoader(valid_corpus).validate()


def test_loader_rejects_fifo(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    fifo = valid_corpus / "plain-answer" / "workspace" / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(CorpusError, match="special_file"):
        CorpusLoader(valid_corpus).validate()


def test_loader_rejects_absolute_and_parent_manifest_paths(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    (valid_corpus / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [{"path": "/tmp/evil", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorpusError, match="illegal_path"):
        CorpusLoader(valid_corpus).validate()

    (valid_corpus / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [{"path": "../outside.txt", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorpusError, match="illegal_path"):
        CorpusLoader(valid_corpus).validate()


def test_loader_rejects_secret_names_and_bearer_values(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    secret_file = valid_corpus / "plain-answer" / "workspace" / "env.txt"
    secret_file.write_text("DEEPSEEK_API_KEY=secret\n", encoding="utf-8")
    _write_manifest(valid_corpus)
    with pytest.raises(CorpusError, match="secret_detected"):
        CorpusLoader(valid_corpus).validate()

    valid_corpus = _copy_valid(tmp_path / "bearer")
    (valid_corpus / "plain-answer" / "workspace" / "token.txt").write_text(
        "Authorization: Bearer abcdefghijklmnop\n",
        encoding="utf-8",
    )
    _write_manifest(valid_corpus)
    with pytest.raises(CorpusError, match="secret_detected"):
        CorpusLoader(valid_corpus).validate()

    valid_corpus = _copy_valid(tmp_path / "glm")
    (valid_corpus / "plain-answer" / "workspace" / "glm.txt").write_text(
        "GLM_API_KEY=another-secret\n",
        encoding="utf-8",
    )
    _write_manifest(valid_corpus)
    with pytest.raises(CorpusError, match="secret_detected"):
        CorpusLoader(valid_corpus).validate()


def test_loader_rejects_non_utf8_json(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    (valid_corpus / "plain-answer" / "case.json").write_bytes(b'{"schema_version":1,\xff}')
    _write_manifest(valid_corpus)
    with pytest.raises(CorpusError, match="invalid_utf8"):
        CorpusLoader(valid_corpus).validate()


def test_loader_keeps_escape_literal_in_script_not_as_filesystem_path(tmp_path: Path) -> None:
    valid_corpus = _copy_valid(tmp_path)
    script = {
        "schema_version": 1,
        "turns": [
            {
                "assistant_text": None,
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "call_id": "c1",
                        "name": "WriteFile",
                        "arguments": {"path": "../outside.txt"},
                    }
                ],
            }
        ],
        "text_deltas": [],
        "approvals": [],
    }
    (valid_corpus / "plain-answer" / "script.json").write_text(
        json.dumps(script),
        encoding="utf-8",
    )
    _write_manifest(valid_corpus)
    loaded = CorpusLoader(valid_corpus).load("plain-answer")
    assert loaded.script.turns[0].tool_calls[0].arguments["path"] == "../outside.txt"


def test_default_corpus_root_is_package_resource() -> None:
    loader = CorpusLoader()
    root = Path(os.fspath(loader.root))
    assert root.name == "corpus"
    assert root.parent.name == "evals"

"""Load and validate the bundled offline evaluation corpus."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from vera.evals.codec import EvalCodec, EvalCodecError
from vera.evals.contracts import (
    CASE_ID_PATTERN,
    EvalCase,
    EvalExpectation,
    EvalScript,
    reject_eval_relative_path,
)

_CASE_ID_RE = re.compile(CASE_ID_PATTERN)
_SECRET_NAMES = ("DEEPSEEK_API_KEY", "GLM_API_KEY", "VERA_LIVE_API_KEY")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-+=/]{8,}")
_IGNORED_DIR_NAMES = {"__pycache__", ".git"}


class CorpusError(ValueError):
    def __init__(self, code: str, source: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.source = source
        self.message = message


def _fail(code: str, source: str, message: str) -> NoReturn:
    raise CorpusError(code, source, message)


@dataclass(frozen=True)
class CorpusValidation:
    manifest_hash: str
    case_ids: tuple[str, ...]
    file_count: int


@dataclass(frozen=True)
class LoadedEvalCase:
    case: EvalCase
    script: EvalScript
    expect: EvalExpectation
    corpus_root: Path
    source_root: Path
    workspace_root: Path
    manifest_hash: str


class CorpusLoader:
    def __init__(self, root: Path | os.PathLike[str] | None = None) -> None:
        if root is None:
            resource = importlib.resources.files("vera.evals").joinpath("corpus")
            self.root: Path = Path(str(resource))
        else:
            self.root = Path(root)

    def validate(self) -> CorpusValidation:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.is_file():
            _fail("missing_manifest", "manifest.json", "corpus manifest is required")
        manifest = _read_manifest(manifest_path)
        listed = _listed_files(manifest)
        discovered = {
            path.relative_to(self.root).as_posix(): path for path in _walk_regular_files(self.root)
        }
        listed_paths = set(listed)
        discovered_paths = set(discovered)
        extra = sorted(discovered_paths - listed_paths)
        if extra:
            _fail("unregistered_file", extra[0], "corpus file is not listed in the manifest")
        missing = sorted(listed_paths - discovered_paths)
        if missing:
            _fail("missing_file", missing[0], "manifest lists a file that is not present")
        for rel, expected_hash in listed.items():
            actual = _sha256_file(discovered[rel])
            if actual != expected_hash:
                _fail("manifest_mismatch", rel, "corpus file hash does not match the manifest")
            _reject_secrets(discovered[rel], rel)
        case_ids = _case_ids(self.root, listed_paths)
        for case_id in case_ids:
            self._load_case(case_id)
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        return CorpusValidation(
            manifest_hash=manifest_hash,
            case_ids=case_ids,
            file_count=len(listed),
        )

    def list_cases(self) -> tuple[EvalCase, ...]:
        validation = self.validate()
        return tuple(self.load(case_id).case for case_id in validation.case_ids)

    def load(self, case_id: str) -> LoadedEvalCase:
        validation = self.validate()
        if case_id not in validation.case_ids:
            _fail("unknown_case", case_id, "case is not present in the corpus")
        return self._load_case(case_id, manifest_hash=validation.manifest_hash)

    def _load_case(
        self,
        case_id: str,
        *,
        manifest_hash: str | None = None,
    ) -> LoadedEvalCase:
        source_root = self.root / case_id
        try:
            case = EvalCodec.decode_case(
                _read_json_bytes(source_root / "case.json", f"{case_id}/case.json"),
                source=f"{case_id}/case.json",
            )
            if case.case_id != case_id:
                _fail(
                    "case_id_mismatch",
                    f"{case_id}/case.json",
                    "case_id must match the directory name",
                )
            script = EvalCodec.decode_script(
                _read_json_bytes(source_root / "script.json", f"{case_id}/script.json"),
                source=f"{case_id}/script.json",
            )
            expect = EvalCodec.decode_expectation(
                _read_json_bytes(source_root / "expect.json", f"{case_id}/expect.json"),
                source=f"{case_id}/expect.json",
            )
        except EvalCodecError as exc:
            raise CorpusError(exc.code, exc.source, exc.message) from exc
        return LoadedEvalCase(
            case=case,
            script=script,
            expect=expect,
            corpus_root=self.root,
            source_root=source_root,
            workspace_root=source_root / "workspace",
            manifest_hash=manifest_hash or "",
        )


def _read_json_bytes(path: Path, source: str) -> bytes:
    try:
        raw = path.read_bytes()
        raw.decode("utf-8")
    except FileNotFoundError as exc:
        raise CorpusError("missing_file", source, "required corpus json is missing") from exc
    except UnicodeDecodeError as exc:
        raise CorpusError("invalid_utf8", source, "corpus json must be utf-8") from exc
    return raw


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise CorpusError("invalid_utf8", "manifest.json", "manifest must be utf-8") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError("invalid_json", "manifest.json", "manifest must be valid json") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        _fail("unsupported_schema", "manifest.json", "manifest schema_version must be 1")
    files = payload.get("files")
    if not isinstance(files, list):
        _fail("invalid_contract", "manifest.json", "manifest files must be a list")
    return payload


def _listed_files(manifest: dict[str, Any]) -> dict[str, str]:
    listed: dict[str, str] = {}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            _fail("invalid_contract", "manifest.json", "manifest file entries must be objects")
        rel = item.get("path")
        digest = item.get("sha256")
        if not isinstance(rel, str) or not isinstance(digest, str):
            _fail(
                "invalid_contract",
                "manifest.json",
                "manifest file entries require path and sha256",
            )
        try:
            normalized = reject_eval_relative_path(rel)
        except ValueError as exc:
            raise CorpusError(
                "illegal_path",
                rel,
                "manifest paths must be relative and stay inside the corpus",
            ) from exc
        if normalized != rel.replace("\\", "/"):
            _fail("illegal_path", rel, "manifest paths must be canonical relative paths")
        if rel in listed:
            _fail("duplicate_path", rel, "manifest paths must be unique")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            _fail("invalid_contract", rel, "manifest sha256 must be 64 lowercase hex")
        listed[rel] = digest
    return listed


def _walk_regular_files(root: Path) -> tuple[Path, ...]:
    return tuple(_iter_regular_files(root))


def iter_corpus_files(root: Path) -> tuple[Path, ...]:
    return _walk_regular_files(root)


def _iter_regular_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    yield from _scan_dir(root, root)


def _scan_dir(root: Path, current: Path) -> Iterator[Path]:
    try:
        entries = list(os.scandir(current))
    except FileNotFoundError:
        return
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.name.startswith(".") or entry.name in _IGNORED_DIR_NAMES:
            continue
        path = Path(entry.path)
        info = entry.stat(follow_symlinks=False)
        mode = info.st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            rel = path.relative_to(root).as_posix()
            _fail("special_file", rel, "corpus must not contain symlinks or special files")
        if stat.S_ISDIR(mode):
            yield from _scan_dir(root, path)
            continue
        if current == root and path.suffix == ".py":
            continue
        if path.name == "manifest.json" and current == root:
            continue
        yield path


def _case_ids(root: Path, listed_paths: set[str]) -> tuple[str, ...]:
    ids: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or entry.name in _IGNORED_DIR_NAMES:
            continue
        if not _CASE_ID_RE.fullmatch(entry.name):
            _fail("illegal_path", entry.name, "case directory names must match case_id")
        case_file = f"{entry.name}/case.json"
        if case_file not in listed_paths:
            _fail("missing_file", case_file, "each case directory must include case.json")
        ids.append(entry.name)
    return tuple(ids)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _reject_secrets(path: Path, rel: str) -> None:
    upper_name = rel.upper()
    if any(name in upper_name for name in _SECRET_NAMES):
        _fail("secret_detected", rel, "corpus paths must not contain provider secret names")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        if path.suffix == ".json":
            _fail("invalid_utf8", rel, "corpus json must be utf-8")
        return
    if any(name in text for name in _SECRET_NAMES) or _BEARER_RE.search(text):
        _fail("secret_detected", rel, "corpus files must not contain provider secrets")

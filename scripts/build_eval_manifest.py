#!/usr/bin/env python3
"""Generate or check the offline evaluation corpus manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from vera.evals.corpus import iter_corpus_files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path) -> dict[str, object]:
    files = []
    for path in iter_corpus_files(root):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"special_file:{rel}")
        files.append({"path": rel, "sha256": _sha256(path)})
    files.sort(key=lambda item: item["path"])
    return {"schema_version": 1, "files": files}


def write_manifest(root: Path) -> None:
    payload = json.dumps(build_manifest(root), indent=2, sort_keys=True) + "\n"
    target = root / "manifest.json"
    temporary = target.with_name("manifest.json.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, target)
    os.chmod(target, 0o600)


def check_manifest(root: Path) -> int:
    target = root / "manifest.json"
    expected = json.dumps(build_manifest(root), indent=2, sort_keys=True) + "\n"
    actual = target.read_text(encoding="utf-8") if target.is_file() else ""
    if actual != expected:
        print("manifest_mismatch", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_eval_manifest.py")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.write:
        write_manifest(root)
        return 0
    return check_manifest(root)


if __name__ == "__main__":
    raise SystemExit(main())

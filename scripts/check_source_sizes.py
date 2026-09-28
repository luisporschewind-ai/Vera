#!/usr/bin/env python3
"""Fail when repository Python source files exceed the refactor size limit."""

from __future__ import annotations

import argparse
from pathlib import Path

MAX_LINES = 600
SCAN_ROOTS = (Path("src/vera"), Path("scripts"), Path("tests"))


def source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for relative_root in SCAN_ROOTS:
        directory = root / relative_root
        if not directory.is_dir():
            continue
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix in {".py", ".pyi"}
        )
    return sorted(files)


def oversized_files(root: Path, *, maximum: int = MAX_LINES) -> list[tuple[Path, int]]:
    oversized: list[tuple[Path, int]] = []
    for path in source_files(root):
        lines = sum(1 for _ in path.open("r", encoding="utf-8"))
        if lines > maximum:
            oversized.append((path, lines))
    return oversized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    violations = oversized_files(root)
    for path, lines in violations:
        print(f"{path.relative_to(root)}: {lines} lines (limit {MAX_LINES})")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())

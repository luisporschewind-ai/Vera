#!/usr/bin/env python3
"""Deterministic workspace check used by representative-project tests."""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write("usage: verify.py NEEDLE RELATIVE_PATH\n")
        return 2
    needle, relative = argv[1], argv[2]
    path = Path(relative)
    if not path.is_file():
        sys.stderr.write(f"missing {relative}\n")
        return 1
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        sys.stderr.write(f"marker not found in {relative}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

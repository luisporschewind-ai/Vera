from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from vera.evals.contracts import FileFact, FileKind
from vera.evals.files import FileInventory, FileInventoryError


def test_inventory_captures_sorted_regular_files_and_directories(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    facts = FileInventory.capture(tmp_path)
    assert [item.path for item in facts] == ["a.txt", "b.txt", "sub"]
    assert facts[0].kind is FileKind.FILE
    assert facts[0].sha256 == hashlib.sha256(b"a\n").hexdigest()
    assert facts[2] == FileFact(path="sub", kind=FileKind.DIRECTORY, size=None, sha256=None)


def test_inventory_rejects_symlink_without_following(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("secret\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(target)
    with pytest.raises(FileInventoryError, match="special_file"):
        FileInventory.capture(tmp_path)


def test_inventory_rejects_fifo(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(FileInventoryError, match="special_file"):
        FileInventory.capture(tmp_path)


def test_inventory_does_not_escape_root(tmp_path: Path) -> None:
    inside = tmp_path / "workspace"
    inside.mkdir()
    (inside / "ok.txt").write_text("ok\n", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("nope\n", encoding="utf-8")
    facts = FileInventory.capture(inside)
    assert [item.path for item in facts] == ["ok.txt"]
    mode = (inside / "ok.txt").stat().st_mode
    assert stat.S_ISREG(mode)

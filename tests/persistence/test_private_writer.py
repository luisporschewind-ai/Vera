from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from vera.persistence.private_writer import (
    PrivateAppendWriter,
    PrivateAtomicWriter,
    PrivateWriteError,
)


def test_write_bytes_does_not_change_existing_parent_mode(tmp_path: Path) -> None:
    parent = tmp_path / "evidence"
    parent.mkdir(mode=0o755)
    os.chmod(parent, 0o755)
    before = stat.S_IMODE(parent.stat().st_mode)
    target = parent / "report.json"
    PrivateAtomicWriter().write_bytes(target, b'{"ok":true}')
    assert stat.S_IMODE(parent.stat().st_mode) == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_bytes() == b'{"ok":true}'


def test_new_directory_is_private_700(tmp_path: Path) -> None:
    target = tmp_path / "created" / "nested" / "file.json"
    PrivateAtomicWriter().write_bytes(target, b"secret")
    assert stat.S_IMODE((tmp_path / "created").stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "created" / "nested").stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_symlink_and_duplicate_targets_fail_closed(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_bytes(b"keep")
    os.chmod(real, 0o644)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    writer = PrivateAtomicWriter()
    with pytest.raises(PrivateWriteError) as linked:
        writer.write_bytes(link, b"nope")
    assert linked.value.code == "symlink_target"
    assert real.read_bytes() == b"keep"
    with pytest.raises(PrivateWriteError) as duplicate:
        writer.write_bytes(real, b"nope")
    assert duplicate.value.code == "target_exists"
    assert real.read_bytes() == b"keep"
    assert stat.S_IMODE(real.stat().st_mode) == 0o644


def test_failed_write_does_not_leave_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "report.json"

    def fail_link(source: str | os.PathLike[str], dest: str | os.PathLike[str]) -> None:
        raise OSError("injected link failure")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(PrivateWriteError) as caught:
        PrivateAtomicWriter().write_bytes(target, b"payload")
    assert caught.value.code == "write_failed"
    assert not target.exists()
    leftovers = list(tmp_path.glob(".*")) + list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_append_line_creates_private_file_and_extends_existing(tmp_path: Path) -> None:
    target = tmp_path / "sessions" / "session_1" / "session.jsonl"
    writer = PrivateAppendWriter()
    writer.append_line(target, b'{"sequence":1}')
    writer.append_line(target, b'{"sequence":2}\n')
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert target.read_text(encoding="utf-8") == '{"sequence":1}\n{"sequence":2}\n'


def test_append_rejects_file_and_parent_symlinks(tmp_path: Path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real_file = real_dir / "session.jsonl"
    real_file.write_text("keep\n", encoding="utf-8")
    file_link = tmp_path / "file-link.jsonl"
    file_link.symlink_to(real_file)
    writer = PrivateAppendWriter()
    with pytest.raises(PrivateWriteError) as linked:
        writer.append_line(file_link, b"nope")
    assert linked.value.code == "symlink_target"
    assert real_file.read_text(encoding="utf-8") == "keep\n"

    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(real_dir)
    with pytest.raises(PrivateWriteError) as parent:
        writer.append_line(parent_link / "session.jsonl", b"nope")
    assert parent.value.code == "symlink_target"
    assert real_file.read_text(encoding="utf-8") == "keep\n"


def test_append_short_write_restores_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session.jsonl"
    writer = PrivateAppendWriter()
    writer.append_line(target, b'{"sequence":1}')
    real_write = os.write

    def short_write(fd: int, data: bytes) -> int:
        if isinstance(data, bytes) and b'"sequence":2' in data:
            return real_write(fd, data[:3])
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", short_write)
    with pytest.raises(PrivateWriteError) as caught:
        writer.append_line(target, b'{"sequence":2}')
    assert caught.value.code == "short_write"
    assert target.read_text(encoding="utf-8") == '{"sequence":1}\n'


def test_append_fsync_failure_restores_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session.jsonl"
    writer = PrivateAppendWriter()
    writer.append_line(target, b'{"sequence":1}')

    def fail_fsync(_fd: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(PrivateWriteError) as caught:
        writer.append_line(target, b'{"sequence":2}')
    assert caught.value.code == "write_failed"
    assert target.read_text(encoding="utf-8") == '{"sequence":1}\n'

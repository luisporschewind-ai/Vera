from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from vera.workspace.paths import (
    PathFact,
    WorkspaceBoundaryError,
    WorkspacePaths,
    kind_from_stat_mode,
)


def test_inspect_rejects_parent_absolute_and_unicode_is_relative(tmp_path: Path) -> None:
    paths = WorkspacePaths(tmp_path)
    (tmp_path / "你好.txt").write_text("ok\n", encoding="utf-8")
    fact = paths.inspect_read("你好.txt")
    assert fact.relative_path == "你好.txt"
    assert fact.kind == "regular"
    assert fact.exists is True
    for value in ("", "/tmp/file", "../file", "sub/../secret"):
        with pytest.raises(WorkspaceBoundaryError) as caught:
            paths.inspect_read(value)
        assert caught.value.code in {"empty_path", "not_workspace_relative"}


def test_inspect_read_allows_internal_link_and_rejects_escape(tmp_path: Path) -> None:
    inside = tmp_path / "inside.txt"
    inside.write_text("ok\n", encoding="utf-8")
    (tmp_path / "internal").symlink_to(inside)
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "escape").symlink_to(outside)
    internal = WorkspacePaths(tmp_path).inspect_read("internal")
    assert internal.kind == "symlink"
    assert Path(internal.canonical_path) == inside.resolve()
    with pytest.raises(WorkspaceBoundaryError) as caught:
        WorkspacePaths(tmp_path).inspect_read("escape")
    assert caught.value.code == "path_escapes_workspace"


def test_inspect_mutation_rejects_symlinks_specials_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("ok\n", encoding="utf-8")
    (tmp_path / "link").symlink_to(target)
    os.mkfifo(tmp_path / "named.pipe")
    socket_path = tmp_path / "sock"
    socket_path.write_text("placeholder\n", encoding="utf-8")
    real_lstat = os.lstat

    def fake_lstat(path: str | os.PathLike[str], *args: object, **kwargs: object) -> os.stat_result:
        result = real_lstat(path, *args, **kwargs)
        if os.path.basename(os.fspath(path)) == "sock":
            mode = stat.S_IFSOCK | stat.S_IMODE(result.st_mode)
            values = list(result)
            values[0] = mode
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "lstat", fake_lstat)
    (tmp_path / "subdir").mkdir()
    paths = WorkspacePaths(tmp_path)
    for name, code in (
        ("link", "symlink_not_allowed"),
        ("named.pipe", "special_file"),
        ("sock", "special_file"),
        ("subdir", "not_regular_file"),
    ):
        with pytest.raises(WorkspaceBoundaryError) as caught:
            paths.inspect_mutation(name)
        assert caught.value.code == code
    absent = paths.inspect_mutation("new.txt")
    assert absent.exists is False
    assert absent.kind == "absent"


def test_device_kind_is_classified_without_opening_a_real_device() -> None:
    assert kind_from_stat_mode(stat.S_IFCHR | 0o666) == "device"
    assert kind_from_stat_mode(stat.S_IFBLK | 0o600) == "device"
    assert kind_from_stat_mode(stat.S_IFIFO | 0o644) == "fifo"
    assert kind_from_stat_mode(stat.S_IFSOCK | 0o777) == "socket"


def test_revalidate_fails_when_inode_or_type_changes(tmp_path: Path) -> None:
    path = tmp_path / "swap.txt"
    path.write_text("first\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    fact = paths.inspect_mutation("swap.txt")
    path.unlink()
    path.write_text("second\n", encoding="utf-8")
    with pytest.raises(WorkspaceBoundaryError) as caught:
        paths.revalidate(fact)
    assert caught.value.code == "fact_mismatch"
    path.unlink()
    path.symlink_to(tmp_path / "other.txt")
    with pytest.raises(WorkspaceBoundaryError) as caught:
        paths.revalidate(fact)
    assert caught.value.code in {"symlink_not_allowed", "fact_mismatch"}
    unavailable = PathFact(
        relative_path="swap.txt",
        canonical_path=str(path),
        exists=True,
        kind="regular",
        device=None,
        inode=None,
        mode=0o644,
        size=4,
        mtime_ns=1,
        content_hash="a" * 64,
        unavailable_fields=("device", "inode"),
    )
    with pytest.raises(WorkspaceBoundaryError) as caught:
        paths.revalidate(unavailable)
    assert caught.value.code == "fact_unavailable"


def test_resolve_helpers_delegate_to_inspect(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("ok\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    assert paths.resolve_read("file.txt") == Path(paths.inspect_read("file.txt").canonical_path)
    assert paths.resolve_mutation("file.txt") == Path(
        paths.inspect_mutation("file.txt").canonical_path
    )
    with pytest.raises(WorkspaceBoundaryError):
        paths.resolve_mutation(".env")

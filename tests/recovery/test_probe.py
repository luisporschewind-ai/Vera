from pathlib import Path

from tests.recovery.helpers import make_snapshot
from vera.contracts.recovery import FileRecoveryState
from vera.recovery.probe import WorkspaceEvidenceProbe, workspace_identity
from vera.workspace.changeset import ABSENT_HASH, sha256_bytes


def test_workspace_identity_is_stable(tmp_path: Path) -> None:
    first = workspace_identity(tmp_path, "install-1")
    second = workspace_identity(tmp_path, "install-1")
    other = workspace_identity(tmp_path, "install-2")
    assert first == second
    assert first != other
    assert len(first) == 64


def test_probe_classifies_exact_hashes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("before\n", encoding="utf-8")
    snapshot = make_snapshot(
        tmp_path,
        files=(("app.py", "update", b"before\n", b"after\n"),),
    )
    probe = WorkspaceEvidenceProbe("install-1")
    assert probe.inspect(snapshot)[0].state is FileRecoveryState.BEFORE

    target.write_text("after\n", encoding="utf-8")
    assert probe.inspect(snapshot)[0].state is FileRecoveryState.AFTER

    target.write_text("user\n", encoding="utf-8")
    assert probe.inspect(snapshot)[0].state is FileRecoveryState.UNKNOWN


def test_probe_create_and_delete_use_absent_hash(tmp_path: Path) -> None:
    snapshot = make_snapshot(
        tmp_path,
        files=(
            ("new.py", "create", b"", b"created\n"),
            ("old.py", "delete", b"old\n", b""),
        ),
        pending=False,
    )
    (tmp_path / "old.py").write_text("old\n", encoding="utf-8")
    probe = WorkspaceEvidenceProbe("install-1")
    evidence = {item.path: item for item in probe.inspect(snapshot)}
    assert evidence["new.py"].state is FileRecoveryState.BEFORE
    assert evidence["new.py"].current_hash == ABSENT_HASH
    assert evidence["old.py"].state is FileRecoveryState.BEFORE

    (tmp_path / "new.py").write_text("created\n", encoding="utf-8")
    (tmp_path / "old.py").unlink()
    evidence = {item.path: item for item in probe.inspect(snapshot)}
    assert evidence["new.py"].state is FileRecoveryState.AFTER
    assert evidence["old.py"].state is FileRecoveryState.AFTER
    assert evidence["old.py"].current_hash == ABSENT_HASH


def test_probe_missing_workspace_is_unknown(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "app.py").write_text("before\n", encoding="utf-8")
    snapshot = make_snapshot(workspace)
    (workspace / "app.py").unlink()
    workspace.rmdir()
    evidence = WorkspaceEvidenceProbe("install-1").inspect(snapshot)
    assert evidence[0].state is FileRecoveryState.UNKNOWN


def test_probe_symlink_escape_is_unknown(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (workspace / "app.py").symlink_to(outside)
    snapshot = make_snapshot(
        workspace,
        files=(("app.py", "update", b"before\n", b"after\n"),),
    )
    evidence = WorkspaceEvidenceProbe("install-1").inspect(snapshot)
    assert evidence[0].state is FileRecoveryState.UNKNOWN
    assert evidence[0].current_hash != sha256_bytes(b"secret\n")

from pathlib import Path

import pytest

from vera.sandbox.access import AccessSession
from vera.workspace.paths import WorkspaceBoundaryError


def test_file_tools_cannot_read_external_content_before_grant(tmp_path: Path) -> None:
    from vera.sandbox.files import PermissionPaths
    from vera.tools.filesystem import read_file

    work = tmp_path / "work"
    work.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("fake outside content")
    session = AccessSession(work)
    paths = PermissionPaths(session)
    assert not read_file(paths, str(secret)).ok
    req = session.request(secret, "read", "session")
    session.resolve(req.request_id, approved=True)
    assert read_file(paths, str(secret)).content == "fake outside content"
    with pytest.raises(WorkspaceBoundaryError):
        paths.inspect_mutation(str(secret))


def test_workspace_private_state_and_symlink_to_secret_are_denied(tmp_path: Path) -> None:
    from vera.sandbox.files import PermissionPaths
    from vera.tools.filesystem import read_file

    private = tmp_path / ".vera"
    private.mkdir()
    (private / "secret.txt").write_text("fake private")
    (tmp_path / "alias").symlink_to(private / "secret.txt")
    paths = PermissionPaths(AccessSession(tmp_path, private_roots=(private,)))
    assert not read_file(paths, ".vera/secret.txt").ok
    assert not read_file(paths, "alias").ok


def test_granted_directory_replacement_does_not_redirect_content(tmp_path: Path) -> None:
    from vera.sandbox.files import PermissionPaths
    from vera.tools.filesystem import read_file

    work = tmp_path / "work"
    work.mkdir()
    directory = tmp_path / "shared"
    directory.mkdir()
    (directory / "file").write_text("approved")
    session = AccessSession(work)
    req = session.request(directory, "read", "session")
    session.resolve(req.request_id, approved=True)
    directory.rename(tmp_path / "old")
    directory.mkdir()
    (directory / "file").write_text("unapproved")
    assert not read_file(PermissionPaths(session), str(directory / "file")).ok

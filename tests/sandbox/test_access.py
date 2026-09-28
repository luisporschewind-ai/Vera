from pathlib import Path

import pytest


def test_unapproved_access_is_denied_without_reading(tmp_path: Path) -> None:
    from vera.sandbox.access import AccessDenied, AccessSession

    workspace = tmp_path / "project"
    workspace.mkdir()
    secret = tmp_path / "private.txt"
    secret.write_text("synthetic only")
    session = AccessSession(workspace)
    with pytest.raises(AccessDenied), session.operation("read-1", ((secret, "read"),)):
        pytest.fail("operation must not begin")


def test_read_grant_is_exact_and_once(tmp_path: Path) -> None:
    from vera.sandbox.access import AccessDenied, AccessSession

    workspace = tmp_path / "project"
    workspace.mkdir()
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("A")
    b.write_text("B")
    session = AccessSession(workspace)
    request = session.request(a, "read", "once", operation_id="op")
    session.resolve(request.request_id, approved=True)
    for path, mode, operation_id in [(a, "write", "op"), (b, "read", "op"), (a, "read", "other")]:
        with pytest.raises(AccessDenied), session.operation(operation_id, ((path, mode),)):
            pass
    with session.operation("op", ((a, "read"),)) as permission:
        assert a.resolve() in permission.readable
        assert a.resolve() not in permission.writable
        assert permission.network == "deny"
    with pytest.raises(AccessDenied), session.operation("op", ((a, "read"),)):
        pass


def test_rejection_and_session_revocation(tmp_path: Path) -> None:
    from vera.sandbox.access import AccessDenied, AccessSession

    workspace = tmp_path / "project"
    workspace.mkdir()
    outside = tmp_path / "external"
    outside.mkdir()
    child = outside / "child"
    child.write_text("fake")
    session = AccessSession(workspace)
    request = session.request(outside, "read_write", "session")
    session.resolve(request.request_id, approved=False)
    with pytest.raises(AccessDenied), session.operation("op", ((child, "read"),)):
        pass
    request = session.request(outside, "read_write", "session")
    grant = session.resolve(request.request_id, approved=True)
    assert grant is not None
    with session.operation("op", ((child, "write"),)):
        pass
    session.revoke(grant.grant_id)
    with pytest.raises(AccessDenied), session.operation("op", ((child, "read"),)):
        pass


def test_symlink_and_directory_replacement_do_not_expand_grant(tmp_path: Path) -> None:
    from vera.sandbox.access import AccessDenied, AccessSession

    workspace = tmp_path / "project"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = tmp_path / "secret"
    secret.write_text("fake")
    (outside / "link").symlink_to(secret)
    session = AccessSession(workspace)
    request = session.request(outside, "read", "session")
    session.resolve(request.request_id, approved=True)
    with pytest.raises(AccessDenied), session.operation("op", ((outside / "link", "read"),)):
        pass
    outside.rename(tmp_path / "moved")
    outside.mkdir()
    (outside / "new").write_text("replacement")
    with pytest.raises(AccessDenied), session.operation("op", ((outside / "new", "read"),)):
        pass


def test_stale_approval_and_private_state_are_rejected(tmp_path: Path) -> None:
    from vera.sandbox.access import AccessDenied, AccessSession

    workspace = tmp_path / "project"
    workspace.mkdir()
    state = workspace / ".vera"
    state.mkdir()
    session = AccessSession(workspace, private_roots=(state,))
    with pytest.raises(AccessDenied):
        session.request(state, "read", "session")
    with pytest.raises(AccessDenied), session.operation("op", ((state / "key", "read"),)):
        pass
    outside = tmp_path / "file"
    outside.write_text("one")
    pending = session.request(outside, "read", "session")
    outside.rename(tmp_path / "old-file")
    outside.write_text("two")
    with pytest.raises(AccessDenied, match="changed"):
        session.resolve(pending.request_id, approved=True)


def test_workspace_baseline_and_closed_session(tmp_path: Path) -> None:
    from vera.sandbox.access import AccessDenied, AccessSession

    session = AccessSession(tmp_path)
    with session.operation("op", ((tmp_path / "new", "write"),)) as permission:
        assert tmp_path.resolve() in permission.writable
    session.close()
    with pytest.raises(AccessDenied), session.operation("op", ((tmp_path / "new", "write"),)):
        pass

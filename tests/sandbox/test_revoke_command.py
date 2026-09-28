from pathlib import Path
from types import SimpleNamespace

from vera.sandbox.access import AccessSession
from vera.session import command_flow, inspection_flow
from vera.tools.command_policy import CommandPolicy


def test_single_grant_revoke_reaches_handler_and_preserves_other_grant(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    access = AccessSession(work)
    grants = []
    for name in ("a", "b"):
        path = tmp_path / name
        path.write_text("fake")
        request = access.request(path, "read", "session")
        grants.append(access.resolve(request.request_id, approved=True))
    # Keep the real slash parser and permissions handler; replace only UI projection.
    host = SimpleNamespace(
        _active_run_id=None,
        _pending_approval=None,
        dependencies=SimpleNamespace(
            runtime=SimpleNamespace(
                access_session=access,
                command_policy=CommandPolicy(),
                workspace_permissions=None,
                process_supervisor=None,
            )
        ),
        _session_event=lambda kind, payload: (kind, payload),
    )
    host._cmd_permissions = lambda args: inspection_flow.permissions(host, args)
    events = list(command_flow.slash(host, f"/permissions revoke-file {grants[0].grant_id}"))
    assert [grant.grant_id for grant in access.grants()] == [grants[1].grant_id]
    assert any(kind == "session.permissions" for kind, _ in events)

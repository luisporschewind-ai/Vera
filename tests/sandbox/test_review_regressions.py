from contextlib import contextmanager
from pathlib import Path

import pytest

from vera.config import ConfigurationError
from vera.process.supervisor import ProcessRequest
from vera.sandbox.access import AccessSession
from vera.sandbox.backend import build_payload
from vera.sandbox.files import PermissionPaths
from vera.sandbox.settings import UnavailableBackend
from vera.sandbox.supervision import SandboxedSupervisor
from vera.tools.filesystem import read_file


@pytest.mark.parametrize(
    "explicit,workspace_contains", [(False, False), (True, False), (False, True)]
)
def test_provider_source_is_never_grantable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool, workspace_contains: bool
) -> None:
    from vera.bootstrap import build_runtime

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    source = home / ("custom-provider.env" if explicit else ".config/vera/deepseek.env")
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "DEEPSEEK_API_KEY=fake-only\nVERA_DEEPSEEK_BASE_URL=https://example.invalid\nVERA_DEEPSEEK_MODEL=fake\n"
    )
    source.chmod(0o600)
    monkeypatch.delenv("VERA_PROVIDER_ENV_FILE", raising=False)
    if explicit:
        monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(source))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(tmp_path / "missing-config"))
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr("vera.bootstrap.load_backend", UnavailableBackend)
    work = source.parent if workspace_contains else tmp_path / "work"
    work.mkdir(exist_ok=True)
    if workspace_contains:
        with pytest.raises(ConfigurationError, match="provider_key_in_workspace"):
            build_runtime(work)
        return
    runtime = build_runtime(work).runtime
    session = runtime.access_session
    assert session is not None
    assert not read_file(PermissionPaths(session), str(source)).ok
    with pytest.raises(ValueError, match="private_resource"):
        session.request(source, "read", "session")


def test_permission_snapshot_cannot_be_retargeted(tmp_path: Path) -> None:
    work = tmp_path / "work"
    allowed = tmp_path / "allowed"
    forbidden = tmp_path / "forbidden"
    for path in (work, allowed, forbidden):
        path.mkdir()
    session = AccessSession(work)
    request = session.request(allowed, "read_write", "session")
    session.resolve(request.request_id, approved=True)
    with session.operation("op", ((allowed, "read"),)) as permissions:
        allowed.rename(tmp_path / "old")
        allowed.symlink_to(forbidden, target_is_directory=True)
        with pytest.raises(ValueError, match="changed"):
            build_payload(
                ProcessRequest(("echo",), work, {}, 1),
                permissions,
                base_readable=(),
                scratch=tmp_path / "scratch",
            )


def test_revalidate_after_profile_generation_before_spawn(tmp_path: Path) -> None:
    work = tmp_path / "work"
    allowed = tmp_path / "allowed"
    forbidden = tmp_path / "forbidden"
    for path in (work, allowed, forbidden):
        path.mkdir()
    session = AccessSession(work)
    request = session.request(allowed, "read", "session")
    session.resolve(request.request_id, approved=True)

    class Backend:
        @contextmanager
        def prepare(self, request, permissions):
            allowed.rename(tmp_path / "old")
            allowed.symlink_to(forbidden, target_is_directory=True)
            yield request

    class Delegate:
        def run(self, *args, **kwargs):
            pytest.fail("must not launch with a replaced grant")

    result = SandboxedSupervisor(session, Backend(), delegate=Delegate()).run(
        ProcessRequest(("echo",), work, {}, 1)
    )
    assert result.status == "error"
    assert b"changed" in result.stderr

import pytest

from vera.sandbox.access import FilePermissions
from vera.sandbox.backend import SandboxError, SrtBackend, isolated_environment


def test_verification_cache_environment_is_preserved_only_inside_write_roots(tmp_path):
    scratch = tmp_path / "scratch"
    artifacts = tmp_path / "artifacts"
    source = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
        "COVERAGE_FILE": str(artifacts / ".coverage"),
        "CLANG_MODULE_CACHE_PATH": str(artifacts / "ModuleCache"),
        "DEVELOPER_DIR": "/untrusted",
        "DYLD_INSERT_LIBRARIES": "/evil",
    }
    env = isolated_environment(source, scratch, writable_roots=(artifacts,))
    for key in (
        "PYTHONDONTWRITEBYTECODE",
        "PYTEST_ADDOPTS",
        "COVERAGE_FILE",
        "CLANG_MODULE_CACHE_PATH",
    ):
        assert env[key] == source[key]
    assert "DEVELOPER_DIR" not in env and "DYLD_INSERT_LIBRARIES" not in env
    assert env["CFFIXED_USER_HOME"] == str(scratch / "home")
    assert env["xcrun_db"] == str(scratch / "cache" / "xcrun")
    assert "COVERAGE_FILE" not in isolated_environment(source, scratch)
    assert "PYTEST_ADDOPTS" not in isolated_environment({"PYTEST_ADDOPTS": "-p evil"}, scratch)


def test_selected_developer_requires_approved_read_and_cannot_be_project_writable(tmp_path):
    developer = tmp_path / "Xcode.app/Contents/Developer"
    developer.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    permissions = FilePermissions(work, (work,), (work,))
    backend = SrtBackend(
        runtime_root=tmp_path / "runtime", base_readable=(), developer_dir=developer
    )
    with pytest.raises(SandboxError, match="sandbox_toolchain_not_approved"):
        backend.toolchain_environment(permissions)
    backend = SrtBackend(
        runtime_root=tmp_path / "runtime",
        base_readable=(developer.parent.parent,),
        developer_dir=developer,
    )
    assert backend.toolchain_environment(permissions) == {"DEVELOPER_DIR": str(developer)}
    permissions = FilePermissions(tmp_path, (tmp_path,), (tmp_path,))
    with pytest.raises(SandboxError, match="sandbox_runtime_writable"):
        backend.toolchain_environment(permissions)


def test_cleanup_failure_preserves_actual_process_result(tmp_path):
    from contextlib import contextmanager

    from vera.process.supervisor import ProcessRequest, ProcessResult
    from vera.sandbox.access import AccessSession
    from vera.sandbox.backend import SandboxCleanupError
    from vera.sandbox.supervision import SandboxedSupervisor

    class Backend:
        @contextmanager
        def prepare(self, request, permissions):
            yield request
            raise SandboxCleanupError(tmp_path / "owned-scratch")

    class Delegate:
        def run(self, request, **kwargs):
            return ProcessResult("exited", 7, b"real-output", b"real-error")

    session = AccessSession(tmp_path)
    result = SandboxedSupervisor(session, Backend(), delegate=Delegate()).run(
        ProcessRequest(("/bin/echo", "fixture"), tmp_path, {}, 5)
    )
    assert result.status == "error"
    assert result.exit_code == 7
    assert result.stdout == b"real-output"
    assert b"real-error" in result.stderr and b"sandbox_cleanup_failed" in result.stderr
    session.close()

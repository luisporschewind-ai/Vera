from pathlib import Path

import pytest

from vera.git.discovery import GitDiscovery, GitDiscoveryError
from vera.process.supervisor import ProcessRequest, ProcessResult, ProcessSupervisor
from vera.sandbox.access import FilePermissions
from vera.sandbox.backend import SandboxError, SrtBackend


def test_selected_git_path_is_available_to_git_children_without_ambient_path(
    tmp_path: Path,
) -> None:
    from vera.sandbox.backend import isolated_environment

    git = tmp_path / "approved" / "git"
    env = isolated_environment(
        {"PATH": "/untrusted", "GIT_EXEC_PATH": "/untrusted", "DEVELOPER_DIR": "/untrusted"},
        tmp_path / "scratch",
        git_executable=git,
    )
    assert env["PATH"] == f"{git.parent}:/usr/bin:/bin:/usr/sbin:/sbin"
    assert "GIT_EXEC_PATH" not in env and "DEVELOPER_DIR" not in env


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (
            b"xcode-select: unable to read /var/select/developer_dir (Operation not permitted)",
            "git_permission_denied",
        ),
        (b"xcode-select: error: No developer tools were found", "git_toolchain_unavailable"),
        (
            b"fatal: not a git repository (or any of the parent directories): .git",
            "git_not_repository",
        ),
        (b"fatal: detected dubious ownership in repository", "git_process_error"),
    ],
)
def test_discovery_classifies_actual_failure(tmp_path: Path, stderr: bytes, expected: str) -> None:
    class FailedProcess(ProcessSupervisor):
        def run(self, request, *, cancel_event=None):
            return ProcessResult("exited", 128, b"", stderr)

    with pytest.raises(GitDiscoveryError) as caught:
        GitDiscovery(tmp_path, supervisor=FailedProcess()).discover()
    assert caught.value.code == expected


def test_explicit_git_requires_exact_read_approval_and_preserves_arguments(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    git = tmp_path / "toolchain" / "git"
    git.parent.mkdir()
    git.write_text("fake binary")
    git.chmod(0o700)
    permissions = FilePermissions(work, (work,), (work,))
    request = ProcessRequest(("git", "-C", str(work), "status"), work, {}, 5)
    backend = SrtBackend(runtime_root=tmp_path / "runtime", base_readable=(), git_executable=git)
    with pytest.raises(SandboxError, match="sandbox_git_not_approved"):
        backend.select_git(request, permissions)
    approved = SrtBackend(
        runtime_root=tmp_path / "runtime", base_readable=(git,), git_executable=git
    )
    selected = approved.select_git(request, permissions)
    assert selected.argv == (str(git), *request.argv[1:])
    assert selected.cwd == request.cwd and selected.env == request.env
    assert selected.timeout_seconds == request.timeout_seconds
    assert approved.select_git(
        ProcessRequest(("/bin/echo", "git"), work, {}, 5), permissions
    ).argv == ("/bin/echo", "git")
    with pytest.raises(SandboxError, match="sandbox_runtime_writable"):
        approved.select_git(request, FilePermissions(tmp_path, (tmp_path,), (tmp_path,)))


def test_selected_git_disappearing_fails_closed(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    git = tmp_path / "missing-git"
    backend = SrtBackend(
        runtime_root=tmp_path / "runtime", base_readable=(git,), git_executable=git
    )
    with (
        pytest.raises(SandboxError, match="sandbox_git_unavailable"),
        backend.prepare(
            ProcessRequest(("/usr/bin/git", "status"), work, {}, 5),
            FilePermissions(work, (work,), (work,)),
        ),
    ):
        pytest.fail("must not fall back to system git")


def test_settings_load_explicit_git_and_legacy_config(tmp_path: Path, monkeypatch) -> None:
    from vera.sandbox import settings

    path = tmp_path / "sandbox.json"
    monkeypatch.setattr(settings, "settings_path", lambda: path)
    git = tmp_path / "git"
    config = settings.SandboxSettings(
        runtime_root=tmp_path / "runtime",
        node=tmp_path / "node",
        base_readable=(git,),
        git_executable=git,
    )
    path.write_text(config.model_dump_json())
    backend = settings.load_backend()
    assert isinstance(backend, SrtBackend)
    assert backend.git_executable == git
    path.write_text(config.model_dump_json(exclude={"git_executable"}))
    legacy = settings.load_backend()
    assert isinstance(legacy, SrtBackend)
    assert legacy.git_executable is None


def test_setup_git_permission_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    import json

    from typer.testing import CliRunner

    from vera import cli_sandbox

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "package.json").write_text(
        json.dumps(
            {
                "name": "@anthropic-ai/sandbox-runtime",
                "version": "0.0.77",
            }
        )
    )
    git = tmp_path / "git"
    git.write_text("fixture")
    git.chmod(0o700)
    node = tmp_path / "node"
    node.write_text("fixture")
    output = tmp_path / "sandbox.json"
    monkeypatch.setattr(cli_sandbox, "settings_path", lambda: output)
    args = [
        "setup",
        "--runtime-root",
        str(runtime),
        "--node",
        str(node),
        "--git-executable",
        str(git),
    ]
    rejected = CliRunner().invoke(cli_sandbox.sandbox_app, args, input="n\n")
    assert rejected.exit_code != 0 and not output.exists()
    assert str(git) in rejected.output
    approved = CliRunner().invoke(cli_sandbox.sandbox_app, args, input="y\n")
    assert approved.exit_code == 0, approved.output
    stored = json.loads(output.read_text())
    assert stored["git_executable"] == str(git)
    assert str(git) in stored["base_readable"]

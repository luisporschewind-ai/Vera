from pathlib import Path
from subprocess import CompletedProcess

from vera.session.models import ConversationStats, GitStatus, SessionStatus
from vera.session.permissions import permission_status
from vera.session.status import SessionStatusService
from vera.tools.command_policy import CommandPolicy


class FakeGitRunner:
    def __init__(
        self,
        *,
        branch: CompletedProcess[str] | Exception | None = None,
        status: CompletedProcess[str] | Exception | None = None,
    ) -> None:
        self.branch = branch
        self.status = status
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CompletedProcess[str]:
        del cwd, timeout
        self.calls.append(argv)
        if "symbolic-ref" in argv:
            if isinstance(self.branch, Exception):
                raise self.branch
            assert self.branch is not None
            return self.branch
        if "status" in argv:
            if isinstance(self.status, Exception):
                raise self.status
            assert self.status is not None
            return self.status
        raise AssertionError(f"unexpected argv: {argv}")


def manual_permissions():
    return permission_status(CommandPolicy())


def test_status_contains_safe_session_fields(tmp_path: Path) -> None:
    runner = FakeGitRunner(
        branch=CompletedProcess([], 0, "main\n", ""),
        status=CompletedProcess([], 0, " M README.md\n", ""),
    )
    service = SessionStatusService(version_reader=lambda: "0.1.0", git_runner=runner)

    status = service.snapshot(
        workspace=tmp_path,
        model_profile="deepseek",
        model_name="deepseek-flash",
        conversation=ConversationStats(
            session_id="session-1",
            message_count=2,
            context_bytes=20,
            max_bytes=200_000,
            warning=False,
            compaction_count=0,
        ),
        permissions=manual_permissions(),
    )

    assert status.workspace == tmp_path.resolve()
    assert status.git.branch == "main"
    assert status.git.dirty is True
    assert status.version == "0.1.0"
    assert status.model_profile == "deepseek"
    assert status.model_name == "deepseek-flash"
    assert "api" not in status.model_dump_json().lower()


def test_status_marks_non_git_workspace(tmp_path: Path) -> None:
    runner = FakeGitRunner(
        branch=CompletedProcess([], 128, "", "fatal: not a git repository"),
        status=CompletedProcess([], 128, "", "fatal: not a git repository"),
    )
    service = SessionStatusService(version_reader=lambda: "0.1.0", git_runner=runner)

    status = service.snapshot(
        workspace=tmp_path,
        model_profile="fake",
        model_name="fake-model",
        conversation=ConversationStats(
            session_id="session-1",
            message_count=0,
            context_bytes=0,
            max_bytes=200_000,
            warning=False,
            compaction_count=0,
        ),
        permissions=manual_permissions(),
    )

    assert status.git == GitStatus(available=False, branch=None, dirty=None)


def test_status_degrades_failed_fields(tmp_path: Path) -> None:
    runner = FakeGitRunner(
        branch=TimeoutError("timed out"),
        status=CompletedProcess([], 0, "", ""),
    )
    service = SessionStatusService(
        version_reader=lambda: (_ for _ in ()).throw(RuntimeError("missing")),
        git_runner=runner,
    )

    status = service.snapshot(
        workspace=tmp_path,
        model_profile="fake",
        model_name="fake-model",
        conversation=ConversationStats(
            session_id="session-1",
            message_count=0,
            context_bytes=0,
            max_bytes=200_000,
            warning=False,
            compaction_count=0,
        ),
        permissions=manual_permissions(),
    )

    assert isinstance(status, SessionStatus)
    assert status.version == "unavailable"
    assert status.git.available is True
    assert status.git.branch is None
    assert status.git.dirty is False

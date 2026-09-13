from pathlib import Path
from subprocess import CompletedProcess

from vera.version import VersionIdentity, inspect_version_identity


class FakeGitRun:
    def __init__(
        self,
        *,
        commit: CompletedProcess[str] | Exception,
        status: CompletedProcess[str] | Exception | None = None,
    ) -> None:
        self.commit = commit
        self.status = status
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float,
    ) -> CompletedProcess[str]:
        del cwd, timeout
        self.calls.append(argv)
        if "rev-parse" in argv:
            if isinstance(self.commit, Exception):
                raise self.commit
            return self.commit
        if "status" in argv:
            if self.status is None:
                raise AssertionError("status not configured")
            if isinstance(self.status, Exception):
                raise self.status
            return self.status
        raise AssertionError(f"unexpected argv: {argv}")


def _editable_layout(tmp_path: Path) -> Path:
    package_dir = tmp_path / "src" / "vera"
    package_dir.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "vera-agent"\n', encoding="utf-8")
    (tmp_path / ".git").mkdir()
    package_file = package_dir / "__init__.py"
    package_file.write_text("", encoding="utf-8")
    return package_file


def test_identity_text_and_json_include_location_and_git(tmp_path: Path) -> None:
    package_file = _editable_layout(tmp_path)
    git_run = FakeGitRun(
        commit=CompletedProcess([], 0, "abc1234\n", ""),
        status=CompletedProcess([], 0, " M src/vera/cli.py\n", ""),
    )

    identity = inspect_version_identity(
        package_file=package_file,
        package_version="0.1.0",
        git_run=git_run,
    )

    assert identity.install == "editable"
    assert identity.display_version == "0.1.0+abc1234.dirty"
    assert identity.location == str(package_file.parent)
    text = identity.to_text()
    assert text.splitlines()[0] == "vera 0.1.0+abc1234.dirty"
    assert str(package_file.parent) in text
    payload = identity.to_payload()
    assert payload["install"] == "editable"
    assert payload["git"] == {"commit": "abc1234", "dirty": True}
    assert git_run.calls[0][0] == "git"
    assert "--porcelain=v1" in git_run.calls[1]
    assert all("symbolic-ref" not in argv for argv in git_run.calls)


def test_wheel_install_omits_git(tmp_path: Path) -> None:
    package_dir = tmp_path / "lib" / "python3.12" / "site-packages" / "vera"
    package_dir.mkdir(parents=True)
    package_file = package_dir / "__init__.py"
    package_file.write_text("", encoding="utf-8")
    git_run = FakeGitRun(commit=Exception("should not run"))

    identity = inspect_version_identity(
        package_file=package_file,
        package_version="0.1.0",
        git_run=git_run,
    )

    assert identity.install == "wheel"
    assert identity.display_version == "0.1.0"
    assert "git" not in identity.to_payload()
    assert git_run.calls == []


def test_git_failure_keeps_package_version(tmp_path: Path) -> None:
    package_file = _editable_layout(tmp_path)
    identity = inspect_version_identity(
        package_file=package_file,
        package_version="0.1.0",
        git_run=FakeGitRun(commit=TimeoutError("timed out")),
    )

    assert identity.install == "editable"
    assert identity.display_version == "0.1.0"
    assert identity.git_commit is None


def test_running_package_points_at_this_tree() -> None:
    identity = inspect_version_identity(package_version="0.1.0")
    assert identity.version == "0.1.0"
    assert identity.location.endswith("vera")
    assert identity.install in {"editable", "wheel", "unknown"}


def test_doctor_detail_does_not_embed_secrets() -> None:
    identity = VersionIdentity(
        name="vera",
        version="0.1.0",
        location="/tmp/vera/src/vera",
        install="editable",
        git_commit="abc1234",
        git_dirty=False,
    )
    dumped = identity.to_text() + identity.doctor_detail() + str(identity.to_payload())
    assert "sk-" not in dumped
    assert "api_key" not in dumped.lower()

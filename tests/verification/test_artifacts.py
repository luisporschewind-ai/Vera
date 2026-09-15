import hashlib
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from vera.contracts.verification import VerificationCommand
from vera.verification.artifacts import (
    VerificationArtifactError,
    VerificationArtifactPlanner,
    VerificationArtifactRoot,
    artifact_root,
    default_verification_prefix,
    environment_for_plan,
    installation_prefix,
)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    return root


def _planner(tmp_path: Path) -> tuple[VerificationArtifactPlanner, Path]:
    prefix = tmp_path / "vera-verification"
    return VerificationArtifactPlanner(prefix=prefix), prefix


def _plan(
    tmp_path: Path,
    argv: tuple[str, ...],
    *,
    index: int = 0,
    run_id: str = "run_1",
    installation_id: str = "install-1",
) -> VerificationCommand:
    planner, _prefix = _planner(tmp_path)
    command = VerificationCommand(argv=argv)
    return planner.plan(
        command,
        workspace_root=_workspace(tmp_path),
        installation_id=installation_id,
        run_id=run_id,
        index=index,
    )


def test_artifact_root_is_deterministic() -> None:
    digest = hashlib.sha256(b"install-1").hexdigest()[:12]
    root = artifact_root(
        workspace_root=Path("/Users/admin/project"),
        installation_id="install-1",
        run_id="run_abc",
        index=7,
    )
    assert root == default_verification_prefix() / digest / "run_abc" / "007"
    if sys.platform == "darwin":
        assert str(root).startswith("/private/tmp/vera-verification/")


def test_artifact_root_rejects_unsafe_bindings(tmp_path: Path) -> None:
    with pytest.raises(VerificationArtifactError) as inside:
        artifact_root(
            workspace_root=default_verification_prefix().parent,
            installation_id="install-1",
            run_id="run_1",
            index=0,
        )
    assert inside.value.code == "verification_output_inside_workspace"

    with pytest.raises(VerificationArtifactError) as separators:
        artifact_root(
            workspace_root=tmp_path,
            installation_id="install-1",
            run_id="run/1",
            index=0,
        )
    assert separators.value.code == "verification_artifact_root_unsafe"

    with pytest.raises(VerificationArtifactError) as negative:
        artifact_root(
            workspace_root=tmp_path,
            installation_id="install-1",
            run_id="run_1",
            index=-1,
        )
    assert negative.value.code == "verification_artifact_root_unsafe"


def test_prepare_creates_0700_root_without_chmoding_existing_parent(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    existing = tmp_path / "vera-verification"
    existing.mkdir(mode=0o755)
    original_mode = stat.S_IMODE(existing.stat().st_mode)
    roots = VerificationArtifactRoot(prefix=existing)
    created = roots.prepare(
        workspace_root=workspace,
        installation_id="install-1",
        run_id="run_1",
        index=0,
    )
    assert created.is_dir()
    assert not created.is_symlink()
    assert stat.S_IMODE(created.stat().st_mode) == 0o700
    assert stat.S_IMODE(existing.stat().st_mode) == original_mode
    parent_run = created.parent
    assert stat.S_IMODE(parent_run.stat().st_mode) == 0o700


def test_prepare_rejects_symlink_parent_and_file_placeholder(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    prefix = tmp_path / "vera-verification"
    prefix.mkdir()
    digest = installation_prefix("install-1")
    linked_parent = prefix / digest
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent.symlink_to(real_parent)
    roots = VerificationArtifactRoot(prefix=prefix)
    with pytest.raises(VerificationArtifactError) as linked:
        roots.prepare(
            workspace_root=workspace,
            installation_id="install-1",
            run_id="run_1",
            index=0,
        )
    assert linked.value.code == "verification_artifact_root_unsafe"

    other = tmp_path / "other-prefix"
    other.mkdir()
    file_root = other / installation_prefix("install-2") / "run_1"
    file_root.mkdir(parents=True)
    (file_root / "000").write_text("not a directory", encoding="utf-8")
    with pytest.raises(VerificationArtifactError) as as_file:
        VerificationArtifactRoot(prefix=other).prepare(
            workspace_root=workspace,
            installation_id="install-2",
            run_id="run_1",
            index=0,
        )
    assert as_file.value.code == "verification_artifact_root_unsafe"


def test_cleanup_only_removes_this_run_index_root(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    prefix = tmp_path / "vera-verification"
    roots = VerificationArtifactRoot(prefix=prefix)
    first = roots.prepare(
        workspace_root=workspace,
        installation_id="install-1",
        run_id="run_1",
        index=0,
    )
    neighbor = roots.prepare(
        workspace_root=workspace,
        installation_id="install-1",
        run_id="run_2",
        index=0,
    )
    sentinel = first / "sentinel.txt"
    sentinel.write_text("drop-me", encoding="utf-8")
    neighbor_file = neighbor / "keep.txt"
    neighbor_file.write_text("keep", encoding="utf-8")
    workspace_file = workspace / "src.txt"
    workspace_file.write_text("source", encoding="utf-8")
    workspace_bytes = workspace_file.read_bytes()

    result = roots.cleanup(first, workspace_root=workspace)
    assert result.status == "cleaned"
    assert not first.exists()
    assert neighbor_file.read_text(encoding="utf-8") == "keep"
    assert workspace_file.read_bytes() == workspace_bytes


def test_cleanup_rejects_symlink_and_broad_paths(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    prefix = tmp_path / "vera-verification"
    roots = VerificationArtifactRoot(prefix=prefix)
    created = roots.prepare(
        workspace_root=workspace,
        installation_id="install-1",
        run_id="run_1",
        index=0,
    )
    linked = tmp_path / "linked-root"
    linked.symlink_to(created)
    assert roots.cleanup(linked, workspace_root=workspace).code == "artifact_cleanup_failed"
    assert created.exists()
    assert roots.cleanup(prefix, workspace_root=workspace).code == "artifact_cleanup_failed"
    assert created.exists()


def test_xcode_scheme_appends_derived_data_path(tmp_path: Path) -> None:
    original = VerificationCommand(
        argv=("xcodebuild", "-project", "Demo.xcodeproj", "-scheme", "Demo", "build")
    )
    planned = _plan(tmp_path, original.argv)
    assert original.argv == ("xcodebuild", "-project", "Demo.xcodeproj", "-scheme", "Demo", "build")
    assert planned.argv[:6] == original.argv
    assert planned.argv[-2:] == ("-derivedDataPath", f"{planned.artifact_plan.root}/DerivedData")
    assert planned.artifact_plan is not None
    assert planned.artifact_plan.profile == "xcode"
    assert planned is not original


def test_xcode_target_appends_external_build_roots(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path,
        ("xcodebuild", "build", "-project", "Demo.xcodeproj", "-target", "Demo"),
    )
    root = Path(planned.artifact_plan.root)  # type: ignore[arg-type]
    assert f"SYMROOT={root / 'Build' / 'Products'}" in planned.argv
    assert f"OBJROOT={root / 'Build' / 'Intermediates'}" in planned.argv
    assert f"SHARED_PRECOMPS_DIR={root / 'Build' / 'SharedPrecomps'}" in planned.argv
    assert f"DSTROOT={root / 'Build' / 'Uninstalled'}" in planned.argv
    env = environment_for_plan(planned.artifact_plan)  # type: ignore[arg-type]
    assert env["CLANG_MODULE_CACHE_PATH"] == str(root / "ModuleCache")


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (
            (
                "xcodebuild",
                "-project",
                "Demo.xcodeproj",
                "-scheme",
                "Demo",
                "-derivedDataPath",
                "build",
            ),
            "verification_output_inside_workspace",
        ),
        (
            (
                "xcodebuild",
                "build",
                "-project",
                "Demo.xcodeproj",
                "-target",
                "Demo",
                "SYMROOT=/Users/admin/Library/Developer",
            ),
            "verification_output_not_owned",
        ),
        (
            (
                "xcodebuild",
                "build",
                "-project",
                "Demo.xcodeproj",
                "-target",
                "Demo",
                f"OBJROOT={tempfile.gettempdir()}/other",
            ),
            "verification_output_not_owned",
        ),
    ],
)
def test_xcode_rejects_unowned_output_paths(
    tmp_path: Path, argv: tuple[str, ...], code: str
) -> None:
    with pytest.raises(VerificationArtifactError) as caught:
        _plan(tmp_path, argv)
    assert caught.value.code == code
    assert caught.value.basename == "xcodebuild"
    assert "SYMROOT=/Users" not in str(caught.value)
    assert "derivedDataPath" not in str(caught.value) or caught.value.code == code


def test_swiftpm_appends_scratch_path(tmp_path: Path) -> None:
    for argv in (
        ("swift", "build"),
        ("swift", "test"),
        ("xcrun", "swift", "test"),
    ):
        planned = _plan(tmp_path, argv, run_id=f"run_{argv[-1]}")
        assert planned.argv[-2:] == ("--scratch-path", f"{planned.artifact_plan.root}/swiftpm")
        assert planned.artifact_plan.profile == "swiftpm"  # type: ignore[union-attr]


def test_swiftpm_existing_scratch_path_must_be_inside_root(tmp_path: Path) -> None:
    with pytest.raises(VerificationArtifactError) as caught:
        _plan(tmp_path, ("swift", "test", "--scratch-path", ".build"))
    assert caught.value.code == "verification_output_inside_workspace"


def test_pytest_and_python_module_get_fixed_environment(tmp_path: Path) -> None:
    for argv in (("pytest", "-q"), ("python", "-m", "pytest", "-q")):
        planned = _plan(tmp_path, argv, run_id=argv[0])
        env = environment_for_plan(planned.artifact_plan)  # type: ignore[arg-type]
        assert planned.argv == argv
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["PYTEST_ADDOPTS"] == "-p no:cacheprovider"
        assert env["COVERAGE_FILE"] == f"{planned.artifact_plan.root}/.coverage"


def test_mypy_appends_cache_dir_and_rejects_workspace_cache(tmp_path: Path) -> None:
    planned = _plan(tmp_path, ("mypy", "src"))
    assert planned.argv[-2:] == ("--cache-dir", f"{planned.artifact_plan.root}/mypy")
    with pytest.raises(VerificationArtifactError) as caught:
        _plan(tmp_path, ("mypy", "src", "--cache-dir", ".mypy_cache"))
    assert caught.value.code == "verification_output_inside_workspace"


def test_ruff_forces_single_no_cache_and_rejects_fix(tmp_path: Path) -> None:
    check = _plan(tmp_path, ("ruff", "check", ".", "--no-cache", "--no-cache"))
    assert check.argv == ("ruff", "check", ".", "--no-cache")
    formatted = _plan(tmp_path, ("ruff", "format", "--check", "src"), run_id="run_format")
    assert formatted.argv[-1] == "--no-cache"
    with pytest.raises(VerificationArtifactError) as caught:
        _plan(tmp_path, ("ruff", "check", "--fix", "."))
    assert caught.value.code == "verification_artifact_isolation_unavailable"


def test_git_readonly_and_tsc_no_emit(tmp_path: Path) -> None:
    git_diff = _plan(tmp_path, ("git", "diff", "--check"))
    git_status = _plan(tmp_path, ("git", "status"), run_id="run_status")
    assert git_diff.artifact_plan.profile == "git_readonly"  # type: ignore[union-attr]
    assert git_status.artifact_plan.profile == "git_readonly"  # type: ignore[union-attr]
    assert environment_for_plan(git_diff.artifact_plan)["GIT_OPTIONAL_LOCKS"] == "0"  # type: ignore[arg-type]
    tsc = _plan(
        tmp_path,
        ("tsc", "--noEmit", "--incremental", "false"),
        run_id="run_tsc",
    )
    assert tsc.artifact_plan.profile == "tsc_no_emit"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "argv",
    [
        ("ruff", "--fix", "src"),
        ("git", "add", "."),
        ("git", "commit", "-m", "x"),
        ("tsc", "--noEmit"),
        ("npm", "run", "build"),
        ("sh", "-c", "pytest"),
        ("unknown-tool", "check"),
    ],
)
def test_unsupported_commands_fail_closed(tmp_path: Path, argv: tuple[str, ...]) -> None:
    with pytest.raises(VerificationArtifactError) as caught:
        _plan(tmp_path, argv)
    assert caught.value.code == "verification_artifact_isolation_unavailable"
    assert caught.value.basename == Path(argv[0]).name
    assert "secret" not in str(caught.value)
    assert caught.value.suggestion

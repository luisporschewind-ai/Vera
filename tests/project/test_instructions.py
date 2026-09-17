from pathlib import Path

import pytest

from vera.content.trust import source_kind_for_path
from vera.contracts.changes import ChangeSet, FileChange
from vera.project_instructions import ProjectInstructionService


def test_vera_md_is_project_guidance() -> None:
    assert source_kind_for_path("VERA.md") == "project_guidance"
    assert source_kind_for_path("vera.md") == "project_guidance"


def test_loads_root_agents_then_vera_with_stable_hash(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("agents base\n", encoding="utf-8")
    (workspace / "VERA.md").write_text("vera extra\n", encoding="utf-8")
    service = ProjectInstructionService()

    loaded = service.load(workspace)
    names = tuple(item.name for item in loaded.sources)
    assert names == ("AGENTS.md", "VERA.md")
    assert loaded.sources[0].priority == 10
    assert loaded.sources[1].priority == 20
    again = service.load(workspace)
    assert again.guidance_hash == loaded.guidance_hash
    assert loaded.issues == ()


@pytest.mark.parametrize(
    "setup, reason",
    [
        ("directory", "unsafe_file_type"),
        ("symlink_inside", "unsafe_file_type"),
        ("symlink_outside", "unsafe_file_type"),
        ("invalid_utf8", "invalid_encoding"),
        ("too_large", "size_limit_exceeded"),
    ],
)
def test_unsafe_or_invalid_files_are_skipped(tmp_path: Path, setup: str, reason: str) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "VERA.md"
    if setup == "directory":
        target.mkdir()
    elif setup == "symlink_inside":
        real = workspace / "real.md"
        real.write_text("inside\n", encoding="utf-8")
        target.symlink_to(real)
    elif setup == "symlink_outside":
        outside = tmp_path / "outside.md"
        outside.write_text("secret-outside\n", encoding="utf-8")
        target.symlink_to(outside)
    elif setup == "invalid_utf8":
        target.write_bytes(b"\xff\xfe not utf8")
    elif setup == "too_large":
        target.write_bytes(b"x" * 32769)
    loaded = ProjectInstructionService().load(workspace)
    assert loaded.sources == ()
    assert loaded.issues[0].name == "VERA.md"
    assert loaded.issues[0].reason_code == reason
    serialized = str(loaded)
    assert "secret-outside" not in serialized
    assert str(tmp_path) not in "".join(issue.name for issue in loaded.issues)


def test_missing_files_are_not_issues(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    loaded = ProjectInstructionService().load(workspace)
    assert loaded.sources == ()
    assert loaded.issues == ()


def test_two_max_size_files_are_accepted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_bytes(b"a" * 32768)
    (workspace / "VERA.md").write_bytes(b"b" * 32768)
    loaded = ProjectInstructionService().load(workspace)
    assert tuple(item.name for item in loaded.sources) == ("AGENTS.md", "VERA.md")
    assert loaded.issues == ()


def test_validate_init_changeset_accepts_only_vera_md() -> None:
    from vera.contracts.verification import VerificationCommand

    service = ProjectInstructionService()
    valid = ChangeSet(
        changeset_id="cs_1",
        run_id="run_1",
        summary="init",
        files=(
            FileChange(
                operation="create",
                path="VERA.md",
                before_hash="0" * 64,
                after_hash="1" * 64,
                unified_diff="--- /dev/null\n+++ VERA.md\n",
            ),
        ),
        verification=(),
        content_hash="2" * 64,
    )
    service.validate_init_changeset(valid)
    with pytest.raises(ValueError, match="project_init_scope_violation"):
        service.validate_init_changeset(
            valid.model_copy(update={"verification": (VerificationCommand(argv=("true",)),)})
        )
    with pytest.raises(ValueError, match="project_init_scope_violation"):
        service.validate_init_changeset(
            valid.model_copy(
                update={
                    "files": (
                        FileChange(
                            operation="create",
                            path="AGENTS.md",
                            before_hash="0" * 64,
                            after_hash="1" * 64,
                            unified_diff="diff",
                        ),
                    )
                }
            )
        )

from pathlib import Path

import pytest

from vera.workspace.mutation import (
    FileMutationApplier,
    FileMutationPlan,
    FileMutationPlanner,
    FileMutationPlanningError,
)
from vera.workspace.paths import WorkspacePaths


def planner(tmp_path: Path) -> FileMutationPlanner:
    return FileMutationPlanner(WorkspacePaths(tmp_path))


def test_plan_write_creates_missing_file_without_writing(tmp_path: Path) -> None:
    planned = planner(tmp_path).plan_write("run-1", "new.txt", "hello\n")

    assert isinstance(planned.plan, FileMutationPlan)
    assert planned.plan.operation == "create"
    assert planned.plan.path == "new.txt"
    assert planned.plan.before_hash == "0" * 64
    assert planned.plan.after_hash == planned.plan.content_hash
    assert planned.after_bytes == b"hello\n"
    assert not (tmp_path / "new.txt").exists()


def test_plan_write_replaces_existing_text_and_binds_expected_hash(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old\n", encoding="utf-8")

    planned = planner(tmp_path).plan_write(
        "run-1", "hello.txt", "new\n", expected_before_hash=planned_hash(b"old\n")
    )

    assert planned.plan.operation == "replace"
    assert planned.plan.before_hash == planned_hash(b"old\n")
    assert "--- a/hello.txt" in planned.plan.unified_diff
    assert target.read_text(encoding="utf-8") == "old\n"


def test_plan_edit_requires_exactly_one_match(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\nold\n", encoding="utf-8")

    for old_text, code in (("missing", "edit_not_found"), ("old", "edit_not_unique")):
        with pytest.raises(FileMutationPlanningError) as caught:
            planner(tmp_path).plan_edit("run-1", "hello.txt", old_text, "new")
        assert caught.value.code == code


def test_planner_rejects_non_utf8_symlink_missing_parent_and_hash_mismatch(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfe")
    (tmp_path / "target.txt").write_text("target", encoding="utf-8")
    try:
        (tmp_path / "link.txt").symlink_to(tmp_path / "target.txt")
    except OSError:
        pytest.skip("symlink creation unavailable")

    cases = (
        (lambda: planner(tmp_path).plan_edit("run-1", "binary.bin", "x", "y"), "non_utf8"),
        (lambda: planner(tmp_path).plan_write("run-1", "link.txt", "x"), "symlink_not_allowed"),
        (lambda: planner(tmp_path).plan_write("run-1", "missing/child.txt", "x"), "parent_missing"),
        (
            lambda: planner(tmp_path).plan_write(
                "run-1", "target.txt", "new", expected_before_hash="0" * 64
            ),
            "before_hash_mismatch",
        ),
        (
            lambda: planner(tmp_path).plan_write("run-1", "../outside.txt", "x"),
            "not_workspace_relative",
        ),
    )
    for operation, code in cases:
        with pytest.raises(FileMutationPlanningError) as caught:
            operation()
        assert caught.value.code == code


def test_applier_checkpoints_applies_and_rolls_back_one_action(
    tmp_path: Path, state_dir: Path
) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    planned = planner(tmp_path).plan_edit("run-1", "hello.txt", "old", "new")
    applier = FileMutationApplier(WorkspacePaths(tmp_path), state_dir)

    applied = applier.apply(planned)

    assert applied.status == "applied"
    assert target.read_text(encoding="utf-8") == "new\n"
    assert (state_dir / "runs" / "run-1" / "mutations" / f"{planned.plan.action_id}.json").exists()

    rolled_back = applier.rollback(planned.plan)
    assert rolled_back.status == "rolled_back"
    assert target.read_text(encoding="utf-8") == "old\n"


def test_applier_rejects_stale_before_fact_without_writing(tmp_path: Path, state_dir: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    planned = planner(tmp_path).plan_edit("run-1", "hello.txt", "old", "new")
    target.write_text("changed\n", encoding="utf-8")

    result = FileMutationApplier(WorkspacePaths(tmp_path), state_dir).apply(planned)

    assert result.status == "stale"
    assert target.read_text(encoding="utf-8") == "changed\n"


def test_applier_replays_same_receipt_without_second_write(tmp_path: Path, state_dir: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    planned = planner(tmp_path).plan_edit("run-1", "hello.txt", "old", "new")

    class CountingWriter:
        def __init__(self) -> None:
            self.calls = 0

        def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
            self.calls += 1
            path.write_bytes(content)

        def delete(self, path: Path) -> None:
            self.calls += 1
            path.unlink(missing_ok=True)

    writer = CountingWriter()
    applier = FileMutationApplier(WorkspacePaths(tmp_path), state_dir, writer=writer)
    assert applier.apply(planned).status == "applied"
    assert applier.apply(planned).status == "applied"
    assert writer.calls == 1


def planned_hash(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()

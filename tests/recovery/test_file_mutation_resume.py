from pathlib import Path

from vera.workspace.mutation import (
    FileMutationApplier,
    FileMutationPlanner,
    FileMutationRecoveryStatus,
)
from vera.workspace.paths import WorkspacePaths


def test_file_mutation_recovery_retries_before_and_confirms_receipted_after(
    tmp_path: Path, state_dir: Path
) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    planned = FileMutationPlanner(WorkspacePaths(tmp_path)).plan_edit(
        "run-1", "hello.txt", "old", "new"
    )
    applier = FileMutationApplier(WorkspacePaths(tmp_path), state_dir)

    before = applier.recover(planned.plan, receipt_matches=False)
    assert before.status is FileMutationRecoveryStatus.RETRY

    target.write_bytes(planned.after_bytes)
    after = applier.recover(planned.plan, receipt_matches=True)
    assert after.status is FileMutationRecoveryStatus.COMPLETED


def test_file_mutation_recovery_requires_manual_review_for_third_bytes(
    tmp_path: Path, state_dir: Path
) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    planned = FileMutationPlanner(WorkspacePaths(tmp_path)).plan_edit(
        "run-1", "hello.txt", "old", "new"
    )
    target.write_text("someone else\n", encoding="utf-8")

    result = FileMutationApplier(WorkspacePaths(tmp_path), state_dir).recover(
        planned.plan, receipt_matches=False
    )

    assert result.status is FileMutationRecoveryStatus.MANUAL_REQUIRED

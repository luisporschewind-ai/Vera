from pathlib import Path

from tests.recovery.helpers import PartialRecoveryFixture
from vera.recovery.planner import RecoveryPlanner
from vera.workspace.apply import RollbackStatus


class _FailingWriter:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
        self.writes.append(str(path))
        raise OSError("writer failed")

    def delete(self, path: Path) -> None:
        raise OSError("writer failed")


def test_partial_restore_only_reverts_after_files(tmp_path: Path) -> None:
    fixture = PartialRecoveryFixture(tmp_path)
    plan = RecoveryPlanner().plan(fixture.report, fixture.snapshot)
    result = fixture.applier.restore_partial(plan, fixture.manifest)

    assert result.status is RollbackStatus.ROLLED_BACK
    assert fixture.before_file.read_bytes() == b"before-a\n"
    assert fixture.after_file.read_bytes() == b"before-b\n"


def test_partial_restore_refuses_unknown_without_writes(tmp_path: Path) -> None:
    fixture = PartialRecoveryFixture(tmp_path)
    plan = RecoveryPlanner().plan(fixture.report, fixture.snapshot)
    before = fixture.before_file.read_bytes()
    after = fixture.after_file.read_bytes()
    fixture.after_file.write_text("changed-after-plan\n", encoding="utf-8")

    result = fixture.applier.restore_partial(plan, fixture.manifest)

    assert result.status is RollbackStatus.RECOVERY_REQUIRED
    assert fixture.before_file.read_bytes() == before
    assert fixture.after_file.read_bytes() == b"changed-after-plan\n"
    assert after == b"after-b\n"


def test_partial_restore_refuses_corrupt_checkpoint_blob(tmp_path: Path) -> None:
    fixture = PartialRecoveryFixture(tmp_path)
    plan = RecoveryPlanner().plan(fixture.report, fixture.snapshot)
    blobs = fixture.state_dir / "runs" / "run_1" / "checkpoint" / "blobs"
    for blob in blobs.glob("*.bin"):
        blob.write_bytes(b"corrupt")
    before = fixture.before_file.read_bytes()
    after = fixture.after_file.read_bytes()

    result = fixture.applier.restore_partial(plan, fixture.manifest)

    assert result.status is RollbackStatus.RECOVERY_REQUIRED
    assert fixture.before_file.read_bytes() == before
    assert fixture.after_file.read_bytes() == after


def test_partial_restore_writer_failure_does_not_claim_success(tmp_path: Path) -> None:
    fixture = PartialRecoveryFixture(tmp_path)
    plan = RecoveryPlanner().plan(fixture.report, fixture.snapshot)
    fixture.applier.writer = _FailingWriter()
    keep = fixture.before_file.read_bytes()

    result = fixture.applier.restore_partial(plan, fixture.manifest)

    assert result.status is RollbackStatus.RECOVERY_REQUIRED
    assert fixture.before_file.read_bytes() == keep
    assert fixture.after_file.read_bytes() == b"after-b\n"

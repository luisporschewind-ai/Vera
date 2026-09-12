from __future__ import annotations

from tests.evals.recovery_helpers import make_recovery_loaded, one_file_proposal
from vera.evals.contracts import EvalScenario
from vera.evals.scenarios import RollbackScenarioRunner


def test_rollback_after_apply_restores_checkpoint_before_hash(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="rollback-after-apply",
        scenario=EvalScenario.ROLLBACK,
        approvals=("approve",),
        turn=one_file_proposal(),
    )
    execution = RollbackScenarioRunner().execute(loaded, isolated)
    assert execution.runtime_instance_count == 1
    assert execution.event_types.count("changeset.applied") == 1
    assert "rollback.completed" in execution.event_types
    assert (isolated.workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
    before = next(item for item in execution.before_files if item.path == "hello.txt")
    after = next(item for item in execution.after_files if item.path == "hello.txt")
    assert after.sha256 == before.sha256

from __future__ import annotations

from tests.evals.recovery_helpers import make_recovery_loaded
from vera.evals.contracts import EvalScenario
from vera.evals.scenarios import RecoveryScenarioRunner
from vera.evals.script_driver import ScriptedRunDriver


def test_resume_after_approval_rebuilds_runtime_and_applies_once(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="resume-after-approval",
        scenario=EvalScenario.RESUME_AFTER_APPROVAL,
    )
    execution = RecoveryScenarioRunner().execute(loaded, isolated)
    assert execution.runtime_instance_count == 2
    assert execution.event_types.count("changeset.applied") == 1
    assert "recovery.detected" in execution.event_types
    assert execution.recovery_classification == "resumable_approval"
    assert "resume" in execution.allowed_actions
    assert (isolated.workspace / "hello.txt").read_text(encoding="utf-8") == "new-hello\n"
    assert (isolated.workspace / "extra.txt").read_text(encoding="utf-8") == "new-extra\n"


def test_in_flight_verification_never_resumes(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="in-flight-manual",
        scenario=EvalScenario.IN_FLIGHT_MANUAL,
    )
    execution = RecoveryScenarioRunner().execute(loaded, isolated)
    assert execution.recovery_classification == "manual_required"
    assert "run.completed" not in execution.event_types_after_restart
    assert "resume" not in execution.allowed_actions
    assert execution.runtime_instance_count == 2


def test_restore_partial_apply_restores_before_bytes(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="restore-partial-apply",
        scenario=EvalScenario.RESTORE_PARTIAL_APPLY,
        approvals=("approve", "approve"),
    )
    execution = RecoveryScenarioRunner().execute(loaded, isolated)
    assert execution.recovery_classification == "recoverable_partial_apply"
    assert "recovery.restored" in execution.event_types
    assert (isolated.workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert not (isolated.workspace / "extra.txt").exists()


def test_idempotent_resume_has_no_duplicate_side_effects(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="idempotent-resume",
        scenario=EvalScenario.IDEMPOTENT_RESUME,
    )
    execution = RecoveryScenarioRunner().execute(loaded, isolated)
    assert execution.event_types.count("changeset.applied") == 1
    assert execution.event_types.count("recovery.resume_started") == 1
    assert execution.runtime_instance_count == 2
    assert execution.event_types[-1] == "run.completed"


def test_wrong_classification_stops_without_resume(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="resume-after-approval",
        scenario=EvalScenario.RESUME_AFTER_APPROVAL,
    )
    from vera.evals import scenarios as scenario_mod
    from vera.evals.failpoints import EvalFailpoint

    scenario_mod._FAILPOINTS[EvalScenario.RESUME_AFTER_APPROVAL] = (
        EvalFailpoint.VERIFICATION_IN_FLIGHT
    )
    try:
        execution = RecoveryScenarioRunner().execute(loaded, isolated)
        assert execution.recovery_classification == "manual_required"
        assert "changeset.applied" not in execution.event_types_after_restart
        assert "recovery.resume_started" not in execution.event_types_after_restart
    finally:
        scenario_mod._FAILPOINTS[EvalScenario.RESUME_AFTER_APPROVAL] = (
            EvalFailpoint.AWAITING_CHANGESET_APPROVAL
        )


def test_scripted_driver_dispatches_recovery_scenarios(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="resume-after-approval",
        scenario=EvalScenario.RESUME_AFTER_APPROVAL,
    )
    execution = ScriptedRunDriver().run(loaded, isolated)
    assert execution.runtime_instance_count == 2
    assert execution.event_types.count("changeset.applied") == 1

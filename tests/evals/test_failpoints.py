from __future__ import annotations

import pytest

from tests.evals.recovery_helpers import make_recovery_loaded, run_until_terminal_or_crash
from vera.contracts.commands import ResumeRun
from vera.evals.contracts import EvalScenario
from vera.evals.failpoints import EvalFailpoint
from vera.evals.runtime_factory import EvalRuntimeFactory
from vera.evals.script_driver import EvalExecutionError
from vera.workspace.apply import SimulatedCrash


@pytest.mark.parametrize(
    "point",
    [
        EvalFailpoint.AWAITING_CHANGESET_APPROVAL,
        EvalFailpoint.AFTER_FIRST_WRITE,
        EvalFailpoint.VERIFICATION_IN_FLIGHT,
        EvalFailpoint.VERIFYING_STABLE,
    ],
)
def test_eval_failpoint_is_one_shot(point: EvalFailpoint, tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="resume-after-approval",
        scenario=EvalScenario.RESUME_AFTER_APPROVAL,
    )
    factory = EvalRuntimeFactory()
    runtime = factory.create(loaded, isolated, failpoint=point)
    with pytest.raises(SimulatedCrash, match=point.value):
        run_until_terminal_or_crash(runtime, loaded, isolated)
    assert factory.trigger_count(point) == 1


def test_standard_case_cannot_enable_failpoint(loaded_and_isolated) -> None:
    loaded, isolated = loaded_and_isolated
    factory = EvalRuntimeFactory()
    with pytest.raises(EvalExecutionError, match="failpoint_not_allowed"):
        factory.create(loaded, isolated, failpoint=EvalFailpoint.AWAITING_CHANGESET_APPROVAL)


def test_unknown_failpoint_string_is_rejected() -> None:
    with pytest.raises(ValueError):
        EvalFailpoint("nope")


def test_second_runtime_has_no_failpoint(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="resume-after-approval",
        scenario=EvalScenario.RESUME_AFTER_APPROVAL,
    )
    factory = EvalRuntimeFactory()
    first = factory.create(loaded, isolated, failpoint=EvalFailpoint.AWAITING_CHANGESET_APPROVAL)
    with pytest.raises(SimulatedCrash):
        run_until_terminal_or_crash(first, loaded, isolated)
    run_id = next(iter(first.runs))
    del first
    second = factory.create(loaded, isolated, failpoint=None, consume_script=False)
    resumed = tuple(second.handle(ResumeRun(run_id=run_id)))
    assert factory.trigger_count(EvalFailpoint.AWAITING_CHANGESET_APPROVAL) == 1
    assert any(event.type == "approval.required" for event in resumed)


def test_partial_write_updates_only_the_first_file(tmp_path) -> None:
    loaded, isolated = make_recovery_loaded(
        tmp_path,
        case_id="restore-partial-apply",
        scenario=EvalScenario.RESTORE_PARTIAL_APPLY,
    )
    factory = EvalRuntimeFactory()
    runtime = factory.create(loaded, isolated, failpoint=EvalFailpoint.AFTER_FIRST_WRITE)
    with pytest.raises(SimulatedCrash, match=EvalFailpoint.AFTER_FIRST_WRITE.value):
        run_until_terminal_or_crash(runtime, loaded, isolated)
    assert (isolated.workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert (isolated.workspace / "extra.txt").read_text(encoding="utf-8") == "new-extra\n"

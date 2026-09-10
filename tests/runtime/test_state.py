import pytest

from vera.runtime.state import IllegalTransition, RunState, RunStateMachine


def test_runtime_rejects_apply_before_checkpoint() -> None:
    machine = RunStateMachine()
    machine.transition(RunState.DISCOVERING)
    with pytest.raises(IllegalTransition):
        machine.transition(RunState.APPLYING)


def test_state_machine_accepts_safe_editing_path() -> None:
    machine = RunStateMachine()
    for state in (
        RunState.DISCOVERING,
        RunState.GENERATING,
        RunState.CHANGESET_PROPOSED,
        RunState.AWAITING_APPROVAL,
        RunState.CHECKPOINTING,
        RunState.APPLYING,
        RunState.VERIFYING,
        RunState.COMPLETED,
    ):
        machine.transition(state)
    assert machine.state is RunState.COMPLETED


def test_terminal_state_has_no_outgoing_transition() -> None:
    machine = RunStateMachine()
    machine.transition(RunState.DISCOVERING)
    machine.transition(RunState.FAILED)
    with pytest.raises(IllegalTransition):
        machine.transition(RunState.CREATED)


def test_run_state_contains_all_fourteen_spec_states() -> None:
    assert len(RunState) == 14

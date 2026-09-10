"""Explicit state machine for one safe-editing run."""

from enum import StrEnum


class RunState(StrEnum):
    CREATED = "created"
    DISCOVERING = "discovering"
    GENERATING = "generating"
    CHANGESET_PROPOSED = "changeset_proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    CHECKPOINTING = "checkpointing"
    APPLYING = "applying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    VERIFICATION_FAILED = "verification_failed"
    CANCELLED = "cancelled"
    STALE = "stale"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"


class IllegalTransition(RuntimeError):
    """Raised when a run attempts a transition not allowed by the contract."""


ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.DISCOVERING, RunState.CANCELLED}),
    RunState.DISCOVERING: frozenset({RunState.GENERATING, RunState.FAILED, RunState.CANCELLED}),
    RunState.GENERATING: frozenset(
        {RunState.DISCOVERING, RunState.CHANGESET_PROPOSED, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.CHANGESET_PROPOSED: frozenset({RunState.AWAITING_APPROVAL, RunState.FAILED}),
    RunState.AWAITING_APPROVAL: frozenset(
        {RunState.CHECKPOINTING, RunState.CANCELLED, RunState.STALE}
    ),
    RunState.CHECKPOINTING: frozenset({RunState.APPLYING, RunState.STALE, RunState.FAILED}),
    RunState.APPLYING: frozenset({RunState.VERIFYING, RunState.FAILED, RunState.RECOVERY_REQUIRED}),
    RunState.VERIFYING: frozenset(
        {RunState.COMPLETED, RunState.VERIFICATION_FAILED, RunState.RECOVERY_REQUIRED}
    ),
    RunState.COMPLETED: frozenset(),
    RunState.VERIFICATION_FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
    RunState.STALE: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.RECOVERY_REQUIRED: frozenset(),
}


class RunStateMachine:
    def __init__(self, state: RunState = RunState.CREATED) -> None:
        self._state = state

    @property
    def state(self) -> RunState:
        return self._state

    def transition(self, target: RunState) -> None:
        if target not in ALLOWED_TRANSITIONS[self._state]:
            raise IllegalTransition(f"{self._state.value} -> {target.value} is not allowed")
        self._state = target

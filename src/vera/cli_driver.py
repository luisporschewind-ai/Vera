"""Terminal-independent driver for a complete Vera run."""

from collections.abc import Callable
from typing import Literal

from vera.contracts.commands import CancelRun, CoreCommand, ResolveApproval
from vera.contracts.events import EventEnvelope
from vera.runtime.engine import VeraRuntime

type ApprovalDecision = Literal["approve", "reject", "cancel"]
type DecisionProvider = Callable[[EventEnvelope], ApprovalDecision]
type EventBatchHandler = Callable[[tuple[EventEnvelope, ...]], None]


def drive_run(
    runtime: VeraRuntime,
    start: CoreCommand,
    decide: DecisionProvider,
    on_events: EventBatchHandler,
) -> tuple[EventEnvelope, ...]:
    """Drive one run through any number of approval boundaries."""

    events: list[EventEnvelope] = []
    command: CoreCommand = start
    while True:
        batch = tuple(runtime.handle(command))
        events.extend(batch)
        on_events(batch)
        approval = next(
            (event for event in reversed(batch) if event.type == "approval.required"),
            None,
        )
        if approval is None:
            return tuple(events)
        decision = decide(approval)
        if decision == "cancel":
            command = CancelRun(run_id=approval.run_id)
        else:
            command = ResolveApproval(
                run_id=approval.run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision=decision,
            )

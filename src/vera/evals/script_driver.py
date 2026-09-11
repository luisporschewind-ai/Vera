"""Drive scripted Core commands for one isolated evaluation case."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from vera.cli_driver import ApprovalDecision, drive_run
from vera.contracts.commands import StartRun
from vera.contracts.events import EventEnvelope
from vera.evals.contracts import EvalScenario, FileFact
from vera.evals.corpus import LoadedEvalCase
from vera.evals.files import FileInventory
from vera.evals.isolation import IsolatedEvalCase
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime

_SIDE_EFFECT_EVENTS = (
    "changeset.applied",
    "rollback.completed",
    "verification.completed",
    "recovery.restored",
)


class EvalExecutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EvalExecution:
    run_ids: tuple[str, ...]
    events: tuple[EventEnvelope, ...]
    before_files: tuple[FileFact, ...]
    after_files: tuple[FileFact, ...]
    runtime_instance_count: int = 1
    restart_event_offset: int | None = None
    side_effect_counts: dict[str, int] | None = None

    @property
    def event_types(self) -> tuple[str, ...]:
        return tuple(event.type for event in self.events)

    @property
    def event_types_after_restart(self) -> tuple[str, ...]:
        if self.restart_event_offset is None:
            return ()
        return self.event_types[self.restart_event_offset :]


class ScriptedRunDriver:
    def execute(
        self,
        runtime: VeraRuntime,
        loaded: LoadedEvalCase,
        isolated: IsolatedEvalCase,
    ) -> EvalExecution:
        if loaded.case.scenario is not EvalScenario.STANDARD:
            raise EvalExecutionError(
                "unsupported_scenario",
                "this evaluation slice only runs standard scenarios",
            )
        before = FileInventory.capture(isolated.workspace)
        approvals = list(loaded.script.approvals)
        events = drive_run(
            runtime,
            StartRun(
                goal=loaded.case.goal,
                workspace_root=isolated.workspace,
                model_profile="fake",
            ),
            decide=_scripted_decider(approvals),
            on_events=lambda _batch: None,
        )
        if approvals:
            raise EvalExecutionError("leftover_approvals", "approval script was not fully consumed")
        adapter = runtime.adapter
        if isinstance(adapter, FakeModelAdapter) and adapter._turns:
            raise EvalExecutionError("leftover_model_turns", "model script was not fully consumed")
        after = FileInventory.capture(isolated.workspace)
        run_ids = tuple(dict.fromkeys(event.run_id for event in events))
        counts = {
            name: sum(1 for event in events if event.type == name) for name in _SIDE_EFFECT_EVENTS
        }
        return EvalExecution(
            run_ids=run_ids,
            events=events,
            before_files=before,
            after_files=after,
            runtime_instance_count=1,
            restart_event_offset=None,
            side_effect_counts=counts,
        )


def _scripted_decider(
    approvals: list[ApprovalDecision],
) -> Callable[[EventEnvelope], ApprovalDecision]:
    def decide(event: EventEnvelope) -> ApprovalDecision:
        del event
        if not approvals:
            raise EvalExecutionError(
                "approval_script_exhausted",
                "no scripted approval remains for this boundary",
            )
        return approvals.pop(0)

    return decide

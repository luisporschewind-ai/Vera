"""Shared fixtures for evaluation recovery and failpoint tests."""

from __future__ import annotations

import sys
from pathlib import Path

from vera.cli_driver import ApprovalDecision
from vera.contracts.commands import CancelRun, ResolveApproval, StartRun
from vera.contracts.events import EventEnvelope
from vera.evals.contracts import EvalCase, EvalExpectation, EvalScenario, EvalScript, EvalTag
from vera.evals.corpus import LoadedEvalCase
from vera.evals.isolation import FixtureIsolator, IsolatedEvalCase
from vera.models.base import ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime


def two_file_proposal(*, verification: bool = True) -> ModelTurn:
    arguments: dict[str, object] = {
        "summary": "edit",
        "changes": [
            {
                "operation": "update",
                "path": "hello.txt",
                "after_content": "new-hello\n",
            },
            {
                "operation": "create",
                "path": "extra.txt",
                "after_content": "new-extra\n",
            },
        ],
    }
    if verification:
        arguments["verification"] = [
            {"argv": [sys.executable, "-c", "print('one')"], "cwd": "."},
            {"argv": [sys.executable, "-c", "print('two')"], "cwd": "."},
        ]
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(ModelToolCall(call_id="1", name="propose_changeset", arguments=arguments),),
    )


def one_file_proposal() -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id="1",
                name="propose_changeset",
                arguments={
                    "summary": "edit",
                    "changes": [
                        {
                            "operation": "update",
                            "path": "hello.txt",
                            "after_content": "new-hello\n",
                        }
                    ],
                },
            ),
        ),
    )


def make_recovery_loaded(
    tmp_path: Path,
    *,
    case_id: str,
    scenario: EvalScenario,
    approvals: tuple[ApprovalDecision, ...] = ("approve",),
    verification: bool = True,
    tags: tuple[EvalTag, ...] = (EvalTag.RECOVERY, EvalTag.CORRECTNESS, EvalTag.SAFETY),
    expect: EvalExpectation | None = None,
    turn: ModelTurn | None = None,
) -> tuple[LoadedEvalCase, IsolatedEvalCase]:
    source = tmp_path / "src" / case_id
    workspace = source / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    loaded = LoadedEvalCase(
        case=EvalCase(
            case_id=case_id,
            title=case_id,
            goal="edit files",
            tags=tags,
            scenario=scenario,
        ),
        script=EvalScript(
            turns=(turn if turn is not None else two_file_proposal(verification=verification),),
            approvals=approvals,
        ),
        expect=expect or EvalExpectation(),
        corpus_root=tmp_path,
        source_root=source,
        workspace_root=workspace,
        manifest_hash="0" * 64,
    )
    isolated = FixtureIsolator(tmp_path / "tmp").prepare(loaded)
    return loaded, isolated


def run_until_terminal_or_crash(
    runtime: VeraRuntime,
    loaded: LoadedEvalCase,
    isolated: IsolatedEvalCase,
) -> tuple[EventEnvelope, ...]:
    events: list[EventEnvelope] = []
    approvals = list(loaded.script.approvals)
    command: StartRun | ResolveApproval | CancelRun = StartRun(
        goal=loaded.case.goal,
        workspace_root=isolated.workspace,
        model_profile="fake",
    )
    while True:
        batch = list(runtime.handle(command))
        events.extend(batch)
        approval = next(
            (event for event in reversed(batch) if event.type == "approval.required"),
            None,
        )
        if approval is None:
            return tuple(events)
        if not approvals:
            raise RuntimeError("approval_script_exhausted")
        decision = approvals.pop(0)
        if decision == "cancel":
            command = CancelRun(run_id=approval.run_id)
        else:
            command = ResolveApproval(
                run_id=approval.run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision=decision,
            )

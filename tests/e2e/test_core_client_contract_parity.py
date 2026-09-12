from __future__ import annotations

from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_driver import drive_run
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.commands import StartRun
from vera.contracts.events import EventEnvelope
from vera.evals.contracts import EvalCase, EvalExpectation, EvalScript, EvalTag
from vera.evals.corpus import LoadedEvalCase
from vera.evals.isolation import FixtureIsolator
from vera.evals.runtime_factory import EvalRuntimeFactory
from vera.evals.script_driver import ScriptedRunDriver
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import ResolveSessionApproval, SubmitPrompt
from vera.session.controller import SessionController
from vera.session.protocol import SessionActionCodec, encode_action
from vera.tools.registry import ToolRegistry


def _proposal() -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id="1",
                name="propose_changeset",
                arguments={
                    "summary": "update hello.txt",
                    "changes": [
                        {
                            "operation": "update",
                            "path": "hello.txt",
                            "after_content": "new\n",
                        }
                    ],
                },
            ),
        ),
    )


def _facts(events: tuple[EventEnvelope, ...]) -> dict[str, object]:
    approvals = [event for event in events if event.type == "approval.required"]
    proposed = [event for event in events if event.type == "changeset.proposed"]
    applied = [event for event in events if event.type == "changeset.applied"]
    failed = [event for event in events if event.type in {"run.failed", "model.failed"}]
    terminal = next(
        (
            event.type
            for event in reversed(events)
            if event.type in {"run.completed", "run.failed", "run.cancelled"}
        ),
        None,
    )
    return {
        "terminal": terminal,
        "approval_kinds": [event.payload.get("kind") for event in approvals],
        "approval_target_hashes": [event.payload.get("target_hash") for event in approvals],
        "changeset_hashes": [event.payload.get("content_hash") for event in proposed],
        "applied": bool(applied),
        "error_codes": [
            event.payload.get("reason") or event.payload.get("reason_code") for event in failed
        ],
        "verification_statuses": [
            event.payload.get("status")
            for event in events
            if event.type == "verification.completed"
        ],
    }


def _runtime(workspace: Path, state_dir: Path) -> VeraRuntime:
    return VeraRuntime(FakeModelAdapter([_proposal()]), ToolRegistry(), state_dir)


def _controller(workspace: Path, state_dir: Path) -> SessionController:
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    runtime = _runtime(workspace, state_dir)
    return SessionController(RuntimeDependencies(runtime=runtime, config=config), workspace, "fake")


def _drive_controller(
    controller: SessionController, *, via_json: bool
) -> tuple[EventEnvelope, ...]:
    submit: SubmitPrompt | object = SubmitPrompt(text="把 hello.txt 改为 new")
    if via_json:
        submit = SessionActionCodec.decode(encode_action(submit))
    collected: list[EventEnvelope] = []
    pending: EventEnvelope | None = None
    for item in controller.dispatch(submit):
        if isinstance(item, EventEnvelope):
            collected.append(item)
            if item.type == "approval.required":
                pending = item
    assert pending is not None
    resolve = ResolveSessionApproval(
        approval_id=str(pending.payload["approval_id"]),
        decision="approve",
    )
    if via_json:
        resolve = SessionActionCodec.decode(encode_action(resolve))
    for item in controller.dispatch(resolve):
        if isinstance(item, EventEnvelope):
            collected.append(item)
    return tuple(collected)


def test_tui_plain_json_and_eval_share_core_facts(tmp_path: Path) -> None:
    goal = "把 hello.txt 改为 new"
    workspace = tmp_path / "plain-ws"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    plain_events = drive_run(
        _runtime(workspace, tmp_path / "plain-state"),
        StartRun(goal=goal, workspace_root=workspace, model_profile="fake"),
        lambda _event: "approve",
        lambda _batch: None,
    )

    tui_ws = tmp_path / "tui-ws"
    tui_ws.mkdir()
    (tui_ws / "hello.txt").write_text("old\n", encoding="utf-8")
    tui_events = _drive_controller(_controller(tui_ws, tmp_path / "tui-state"), via_json=False)

    json_ws = tmp_path / "json-ws"
    json_ws.mkdir()
    (json_ws / "hello.txt").write_text("old\n", encoding="utf-8")
    json_events = _drive_controller(_controller(json_ws, tmp_path / "json-state"), via_json=True)

    source = tmp_path / "eval-src"
    source_ws = source / "workspace"
    source_ws.mkdir(parents=True)
    (source_ws / "hello.txt").write_text("old\n", encoding="utf-8")
    loaded = LoadedEvalCase(
        case=EvalCase(
            case_id="parity-update",
            title="parity",
            goal=goal,
            tags=(EvalTag.CORRECTNESS,),
        ),
        script=EvalScript(turns=(_proposal(),), approvals=("approve",)),
        expect=EvalExpectation(),
        corpus_root=tmp_path,
        source_root=source,
        workspace_root=source_ws,
        manifest_hash="0" * 64,
    )
    isolated = FixtureIsolator(tmp_path / "eval-iso").prepare(loaded)
    eval_events = (
        ScriptedRunDriver()
        .execute(
            EvalRuntimeFactory().create(loaded, isolated),
            loaded,
            isolated,
        )
        .events
    )

    expected = _facts(plain_events)
    assert expected["terminal"] == "run.completed"
    assert expected["applied"] is True
    assert expected["changeset_hashes"]
    assert _facts(tui_events) == expected
    assert _facts(json_events) == expected
    assert _facts(eval_events) == expected
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (tui_ws / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (json_ws / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (isolated.workspace / "hello.txt").read_text(encoding="utf-8") == "new\n"

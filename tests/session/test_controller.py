from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import CancelActiveRun, CloseSession, SubmitPrompt
from vera.session.controller import SessionController
from vera.tools.registry import ToolRegistry


def make_controller(workspace: Path, turns: list[ModelTurn]) -> SessionController:
    state_dir = workspace.parent / "state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(max_conversation_bytes=200_000),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    runtime = VeraRuntime(FakeModelAdapter(turns), ToolRegistry(), state_dir)
    deps = RuntimeDependencies(runtime=runtime, config=config)
    return SessionController(deps, workspace, "fake")


def proposal(call_id: str, content: str) -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id=call_id,
                name="propose_changeset",
                arguments={
                    "summary": "edit",
                    "changes": [
                        {
                            "operation": "update",
                            "path": "hello.txt",
                            "after_content": content,
                        }
                    ],
                },
            ),
        ),
    )


def test_controller_submits_prompt_through_runtime(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(
        workspace,
        [ModelTurn(assistant_text="解释完成", finish_reason="stop")],
    )

    outputs = tuple(controller.dispatch(SubmitPrompt(text="解释这个项目")))

    assert any(
        isinstance(item, EventEnvelope) and item.type == "run.completed" for item in outputs
    )
    assert controller.active_run_id is None


def test_controller_rejects_second_prompt_while_run_active(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    controller.mark_active("run_1")

    outputs = tuple(controller.dispatch(SubmitPrompt(text="second")))

    assert outputs[-1].type == "session.action_rejected"
    assert outputs[-1].payload["reason_code"] == "run_active"


def test_controller_pauses_on_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])

    outputs = tuple(controller.dispatch(SubmitPrompt(text="edit")))

    assert any(isinstance(item, EventEnvelope) and item.type == "approval.required" for item in outputs)
    assert controller.pending_approval_id is not None
    assert controller.active_run_id is not None


def test_cancel_is_idempotent_when_idle(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])

    outputs = tuple(controller.dispatch(CancelActiveRun(run_id="missing")))

    assert outputs[-1].type == "session.action_rejected"
    assert outputs[-1].payload["reason_code"] == "no_active_run"


def test_close_cancels_pending_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    tuple(controller.dispatch(SubmitPrompt(text="edit")))
    assert controller.pending_approval_id is not None

    outputs = tuple(controller.dispatch(CloseSession()))

    assert any(isinstance(item, EventEnvelope) and item.type == "run.cancelled" for item in outputs)
    assert any(isinstance(item, EventEnvelope) and item.type == "session.closed" for item in outputs)
    assert controller.snapshot().closed is True
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"

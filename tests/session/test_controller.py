from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import (
    CancelActiveRun,
    ClearQueuedPrompt,
    CloseSession,
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
    ResolveSessionApproval,
    SubmitPrompt,
)
from vera.session.controller import SessionController
from vera.tools.registry import ToolRegistry


def make_controller(
    workspace: Path,
    turns: list[ModelTurn],
    *,
    editor_argv: tuple[str, ...] = (),
) -> SessionController:
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
        editor_argv=editor_argv,
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

    prompt = next(
        item
        for item in outputs
        if isinstance(item, EventEnvelope) and item.type == "session.user_prompt"
    )
    assert prompt.payload["text"] == "解释这个项目"
    assert any(isinstance(item, EventEnvelope) and item.type == "run.completed" for item in outputs)
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

    assert any(
        isinstance(item, EventEnvelope) and item.type == "approval.required" for item in outputs
    )
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
    assert any(
        isinstance(item, EventEnvelope) and item.type == "session.closed" for item in outputs
    )
    assert controller.snapshot().closed is True
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_queue_prompt_waits_for_terminal_then_starts_new_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(
        workspace,
        [
            ModelTurn(assistant_text="first", finish_reason="stop"),
            ModelTurn(assistant_text="second", finish_reason="stop"),
        ],
    )
    controller.mark_active("run_1")

    queued = tuple(controller.dispatch(QueuePrompt(text="follow up")))
    assert queued[-1].type == "session.prompt_queued"
    assert controller.queued_prompt == "follow up"
    occupied = tuple(controller.dispatch(QueuePrompt(text="other")))
    assert occupied[-1].payload["reason_code"] == "queue_occupied"
    cleared = tuple(controller.dispatch(ClearQueuedPrompt()))
    assert cleared[-1].type == "session.prompt_queue_cleared"
    tuple(controller.dispatch(QueuePrompt(text="follow up")))

    controller._active_run_id = None
    outputs = tuple(controller.dispatch(SubmitPrompt(text="first")))
    types = [item.type for item in outputs if isinstance(item, EventEnvelope)]
    assert "run.completed" in types
    assert "session.prompt_queue_flushed" in types
    assert types.count("run.completed") == 2
    assert controller.queued_prompt is None
    assert controller.active_run_id is None


def test_queue_rejected_during_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    tuple(controller.dispatch(SubmitPrompt(text="edit")))
    assert controller.pending_approval_id is not None

    outputs = tuple(controller.dispatch(QueuePrompt(text="next")))
    assert outputs[-1].type == "session.action_rejected"
    assert outputs[-1].payload["reason_code"] == "approval_pending"
    assert controller.queued_prompt is None


def test_close_clears_in_memory_history_and_queue(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    controller.mark_active("run_1")
    tuple(controller.dispatch(QueuePrompt(text="queued")))
    controller.history.record("remembered")
    tuple(controller.dispatch(CloseSession()))
    assert len(controller.history) == 0
    assert controller.queued_prompt is None


def test_external_editor_requires_preview_then_returns_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [], editor_argv=("/usr/bin/true",))
    preview = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert preview[-1].type == "session.editor_preview"
    assert preview[-1].payload["needs_confirmation"] is True
    tuple(controller.dispatch(ConfirmExternalEditor(accept=True)))
    closed = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert closed[-1].type == "session.editor_closed"
    assert closed[-1].payload["status"] == "unchanged"


def test_external_editor_rejects_unconfigured_argv(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    outputs = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert outputs[-1].payload["reason_code"] == "editor_unconfigured"


def test_new_slash_commands_are_structured_and_unknown_is_not_executed(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    help_event = tuple(controller.dispatch(ExecuteSlashCommand(raw="/help")))[-1]
    assert help_event.type == "session.help"
    assert "代码与证据" in str(help_event.payload["text"])
    unknown = tuple(controller.dispatch(ExecuteSlashCommand(raw="/docotr")))[-1]
    assert unknown.type == "session.message"
    assert "/doctor" in str(unknown.payload.get("suggestions"))
    doctor = tuple(controller.dispatch(ExecuteSlashCommand(raw="/doctor")))[-1]
    assert doctor.type == "session.doctor"
    usage = tuple(controller.dispatch(ExecuteSlashCommand(raw="/usage")))[-1]
    assert usage.payload["calls"] == "unavailable"
    theme = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme high-contrast")))[-1]
    assert theme.payload["theme"] == "high-contrast"
    assert "当前主题：high-contrast" in str(theme.payload["text"])
    listed = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme")))[-1]
    assert listed.payload["theme"] == "high-contrast"
    unknown_theme = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme neon")))[-1]
    assert unknown_theme.type == "session.message"
    assert "未知主题" in str(unknown_theme.payload["text"])
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    assert diff.payload["files"] == []
    review = tuple(controller.dispatch(ExecuteSlashCommand(raw="/review")))[-1]
    assert review.type == "session.review"


def test_diff_after_completed_run_uses_last_changeset(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    started = tuple(controller.dispatch(SubmitPrompt(text="edit hello")))
    pending = next(
        item
        for item in started
        if isinstance(item, EventEnvelope) and item.type == "approval.required"
    )
    tuple(
        controller.dispatch(
            ResolveSessionApproval(
                approval_id=str(pending.payload["approval_id"]),
                decision="approve",
            )
        )
    )
    assert controller.active_run_id is None
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    files = diff.payload["files"]
    assert isinstance(files, list) and files
    assert files[0]["path"] == "hello.txt"
    text = str(diff.payload.get("text", ""))
    assert "hello.txt" in text
    assert "没有 Diff。" not in text
    assert diff.payload.get("applied") is True
    assert "未写入工作区" not in text


def test_diff_before_apply_is_labeled_unwritten(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    tuple(controller.dispatch(SubmitPrompt(text="edit hello")))
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    assert diff.payload.get("applied") is False
    assert "未写入工作区" in str(diff.payload.get("text", ""))
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"

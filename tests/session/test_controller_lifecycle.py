import threading
from pathlib import Path

from tests.session.controller_helpers import (
    make_controller,
    proposal,
)
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.session.actions import (
    CancelActiveRun,
    ClearQueuedPrompt,
    CloseSession,
    ExecuteSlashCommand,
    QueuePrompt,
    SubmitPrompt,
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
    stats = controller.conversation_stats()
    assert stats.context_bytes > 0
    status = next(
        item
        for item in controller.dispatch(ExecuteSlashCommand(raw="/status"))
        if isinstance(item, EventEnvelope) and item.type == "session.status"
    )
    assert status.payload["context"]["context_bytes"] == stats.context_bytes
    assert status.payload["context"]["max_bytes"] == stats.max_bytes


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


def test_cancel_does_not_resurrect_run_or_reject_flushed_queue(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class GatedAdapter(FakeModelAdapter):
        def __init__(self) -> None:
            super().__init__(
                [
                    ModelTurn(assistant_text="first", finish_reason="stop"),
                    ModelTurn(assistant_text="second", finish_reason="stop"),
                ]
            )
            self.started = threading.Event()
            self.release = threading.Event()

        def stream(self, request):  # type: ignore[no-untyped-def]
            if not self.started.is_set():
                self.started.set()
                assert self.release.wait(timeout=2.0)
            yield from super().stream(request)

    adapter = GatedAdapter()
    controller = make_controller(workspace, [], adapter=adapter)
    errors: list[Exception] = []

    def submit() -> None:
        try:
            tuple(controller.dispatch(SubmitPrompt(text="one")))
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=submit)
    worker.start()
    assert adapter.started.wait(timeout=2.0)
    assert controller.active_run_id is not None
    tuple(controller.dispatch(QueuePrompt(text="two")))
    cancel = tuple(controller.dispatch(CancelActiveRun(run_id=controller.active_run_id)))
    adapter.release.set()
    worker.join(timeout=2.0)
    types = [item.type for item in cancel if isinstance(item, EventEnvelope)]
    assert "run.cancelled" in types
    assert not any(
        isinstance(item, EventEnvelope)
        and item.type == "session.action_rejected"
        and item.payload.get("reason_code") == "run_active"
        for item in cancel
    )
    assert errors == []
    assert worker.is_alive() is False


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

import threading
from pathlib import Path

from vera.contracts.commands import CancelRun, StartRun
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


class GatedAdapter(FakeModelAdapter):
    def __init__(self) -> None:
        super().__init__([ModelTurn(assistant_text="late", finish_reason="stop")])
        self.started = threading.Event()
        self.release = threading.Event()

    def stream(self, request):  # type: ignore[no-untyped-def]
        self.started.set()
        assert self.release.wait(timeout=2.0)
        yield from super().stream(request)


def test_cancel_during_model_call_does_not_complete_or_raise(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = GatedAdapter()
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    types: list[str] = []
    errors: list[Exception] = []

    def run() -> None:
        try:
            for item in runtime.stream(
                StartRun(goal="hi", workspace_root=workspace, model_profile="fake")
            ):
                if isinstance(item, EventEnvelope):
                    types.append(item.type)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert adapter.started.wait(timeout=2.0)
    run_id = next(iter(runtime.runs))
    cancelled = [item.type for item in runtime.handle(CancelRun(run_id=run_id))]
    adapter.release.set()
    worker.join(timeout=2.0)
    assert "run.cancelled" in cancelled
    assert "run.completed" not in types
    assert errors == []
    assert worker.is_alive() is False

import json
import subprocess
from pathlib import Path

import pytest

from tests.cli.test_session import make_session
from vera.models.base import ModelTurn
from vera.process.supervisor import ProcessRequest, ProcessSupervisor


def test_paste_is_one_prompt_and_keeps_approval_word_as_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, adapter, _ = make_session(
        workspace,
        [ModelTurn(finish_reason="stop", assistant_text="done")],
        ["/paste", "first", "", "approve", "last", "/end", "/exit"],
    )
    assert session.run() == 0
    assert len(adapter.requests) == 1
    assert any(
        json.loads(m.content).get("data") == "first\n\napprove\nlast"
        for m in adapter.requests[0].messages
        if m.role == "user"
    )


def test_interrupted_paste_does_not_submit_partial_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, adapter, _ = make_session(
        workspace, [], ["/paste", "partial", KeyboardInterrupt(), "/exit"]
    )
    assert session.run() == 0
    assert not adapter.requests


def test_interrupt_during_run_returns_to_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, _, io = make_session(workspace, [], ["work", "/exit"])
    original = session.controller.dependencies.runtime.adapter.stream

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    session.controller.dependencies.runtime.adapter.stream = interrupted
    try:
        assert session.run() == 0
    finally:
        session.controller.dependencies.runtime.adapter.stream = original
    assert session.controller.active_run_id is None
    assert "取消" in "\n".join(io.output)


def test_interrupted_supervisor_reaps_its_process(tmp_path: Path) -> None:
    processes = []

    def spawn(*args, **kwargs):
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        return process

    class InterruptedSupervisor(ProcessSupervisor):
        def _wait(self, *args, **kwargs):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        InterruptedSupervisor(process_factory=spawn, strict_group=True).run(
            ProcessRequest(("/bin/sleep", "30"), tmp_path, {}, 60)
        )
    assert len(processes) == 1
    assert processes[0].poll() is not None

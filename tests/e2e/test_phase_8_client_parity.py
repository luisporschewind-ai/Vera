from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from vera.cli_presenter import HumanPresenter
from vera.contracts.events import EventEnvelope
from vera.presentation.projector import AppendBlock, TimelineProjector
from vera.session.protocol import SessionRecord, SessionRecordCodec


def _events() -> tuple[EventEnvelope, ...]:
    return tuple(
        EventEnvelope(
            event_id=f"e{index}",
            run_id="run-phase8",
            sequence=index,
            timestamp=datetime.now(UTC),
            type=event_type,
            payload=payload,
        )
        for index, (event_type, payload) in enumerate(
            (
                ("git.operation.started", {"operation": "git_commit"}),
                ("git.operation.completed", {"operation": "git_commit", "ok": True}),
                ("git.operation.recovered", {"operation": "git_commit", "ok": True}),
                (
                    "git.operation.manual_required",
                    {"operation": "git_commit", "error_code": "manual_required"},
                ),
            ),
            start=1,
        )
    )


def test_phase8_tui_plain_json_preserve_same_git_facts() -> None:
    events = _events()
    plain: list[str] = []
    HumanPresenter(plain.append).write_events(events)
    projector = TimelineProjector()
    blocks = [
        mutation.block
        for event in events
        for mutation in projector.apply(event)
        if isinstance(mutation, AppendBlock)
    ]
    json_events = [
        json.loads(SessionRecordCodec.encode(SessionRecord(record_type="event", event=event)))
        for event in events
    ]

    assert "Git 操作已恢复" in plain
    assert any(block.title == "Git 操作需要人工恢复" for block in blocks)
    assert [item["event"]["type"] for item in json_events] == [event.type for event in events]
    assert json_events[-1]["event"]["payload"]["error_code"] == "manual_required"


def test_phase8_clean_install_imports_recovery_before_git_without_cycle() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    result = subprocess.run(
        [sys.executable, "-c", "from vera.recovery.probe import workspace_identity"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

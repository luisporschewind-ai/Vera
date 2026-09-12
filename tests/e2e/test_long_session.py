"""Long-session memory bounds for context, events, and terminal projection."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from vera.config import Limits
from vera.contracts.commands import StartRun
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.presentation.projector import TimelineProjector
from vera.presentation.timeline import BlockKind
from vera.runtime.engine import VeraRuntime
from vera.session.conversation import ConversationContext
from vera.tools.definitions import ToolResult
from vera.tools.filesystem import read_file
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


class ReadInput(BaseModel):
    path: str


class ReadTool:
    name = "read_file"
    input_model = ReadInput

    def __init__(self, root: Path) -> None:
        self.paths = WorkspacePaths(root)

    def execute(self, arguments: ReadInput) -> ToolResult:
        return read_file(self.paths, arguments.path)


def test_long_session_keeps_fact_refs_without_linear_full_text(tmp_path: Path) -> None:
    payload = ("LINE\n" * 40) + "Bearer sk-live-long-session-secret-abcdef"
    for index in range(500):
        (tmp_path / f"n{index}.txt").write_text(
            payload if index == 0 else f"LINE {index}\n" * 20,
            encoding="utf-8",
        )
    registry = ToolRegistry()
    registry.register(ReadTool(tmp_path))
    turns = [
        ModelTurn(
            finish_reason="tool_calls",
            tool_calls=tuple(
                ModelToolCall(
                    call_id=str(index),
                    name="read_file",
                    arguments={"path": f"n{index}.txt"},
                )
                for index in range(500)
            ),
        ),
        ModelTurn(assistant_text="已阅读工作区。", finish_reason="stop"),
    ]
    runtime = VeraRuntime(
        FakeModelAdapter(turns),
        registry,
        tmp_path / "state",
        limits=Limits(
            max_model_turns=600,
            max_tool_calls=600,
            max_context_bytes=40_000,
            max_file_bytes=8_192,
        ),
    )
    events = list(
        runtime.handle(
            StartRun(goal="inspect notes", workspace_root=tmp_path, model_profile="fake")
        )
    )
    context = runtime.runs[events[0].run_id]
    full_text_hits = sum(message.content.count("LINE") for message in context.messages)
    assert full_text_hits < 500 * 200
    assert "sk-live-long-session-secret-abcdef" not in "\n".join(
        message.content for message in context.messages
    )
    assert "\x1b" not in "\n".join(message.content for message in context.messages)
    assert any(
        "vera_content" in message.content and "content_hash" in message.content
        for message in context.messages
        if message.role == "tool"
    )
    assert events[-1].type == "run.completed", events[-1].payload

    conversation = ConversationContext(8_000, max_items=24)
    for index in range(100):
        conversation.record_run(
            f"turn {index}",
            (
                EventEnvelope(
                    event_id=f"e{index}a",
                    run_id=f"run_{index}",
                    sequence=1,
                    timestamp=events[0].timestamp,
                    type="changeset.proposed",
                    payload={
                        "changeset_id": f"cs_{index}",
                        "files": [
                            {
                                "path": f"View{index}.swift",
                                "operation": "update",
                                "unified_diff": payload,
                            }
                        ],
                    },
                ),
                EventEnvelope(
                    event_id=f"e{index}b",
                    run_id=f"run_{index}",
                    sequence=2,
                    timestamp=events[0].timestamp,
                    type="run.completed",
                    payload={"state": "completed", "outcome": "changed"},
                ),
            ),
        )
    serialized = "\n".join(message.content for message in conversation.snapshot())
    assert conversation.stats().message_count <= 24
    assert "cs_99" in serialized
    assert "View99.swift" in serialized
    assert payload not in serialized
    assert "sk-live-long-session-secret-abcdef" not in serialized

    projector = TimelineProjector(max_body_bytes=512, max_blocks=30)
    huge = "row\n" * 10_000
    projector.apply(
        EventEnvelope(
            event_id="diff",
            run_id="run_proj",
            sequence=1,
            timestamp=events[0].timestamp,
            type="changeset.proposed",
            payload={"files": [{"path": "App.swift", "unified_diff": huge}]},
        )
    )
    projector.apply(
        EventEnvelope(
            event_id="approval",
            run_id="run_proj",
            sequence=2,
            timestamp=events[0].timestamp,
            type="approval.required",
            payload={"approval_id": "pending_1", "risk": "low"},
        )
    )
    projector.apply(
        EventEnvelope(
            event_id="fail",
            run_id="run_proj",
            sequence=3,
            timestamp=events[0].timestamp,
            type="run.failed",
            payload={"reason": "verification_failed"},
        )
    )
    for index in range(40):
        projector.apply(
            EventEnvelope(
                event_id=f"tool{index}",
                run_id="run_proj",
                sequence=4 + index,
                timestamp=events[0].timestamp,
                type="tool.completed",
                payload={"name": "read_file", "ok": True, "result": huge},
            )
        )
    kinds = {block.kind for block in projector.blocks()}
    assert BlockKind.DIFF in kinds
    assert BlockKind.APPROVAL in kinds
    assert BlockKind.ERROR in kinds
    assert len(projector.blocks()) <= 30
    assert all(len(block.body.encode("utf-8")) <= 512 for block in projector.blocks())

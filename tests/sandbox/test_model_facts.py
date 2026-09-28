import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from vera.contracts.commands import ResolveApproval, StartRun
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.session_store import ConversationSessionStore
from vera.redaction import Redactor
from vera.runtime.engine import VeraRuntime
from vera.sandbox.access import AccessSession
from vera.sandbox.files import PermissionPaths
from vera.sandbox.tools import RequestFileAccessTool
from vera.session.conversation import ConversationContext
from vera.session.persistence_flow import persist_compaction
from vera.session.turns import ConversationTurnProjector
from vera.tools.builtin import ReadTool
from vera.tools.registry import ToolRegistry


def tool_turn(name, arguments):
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(ModelToolCall(call_id="call-test", name=name, arguments=arguments),),
    )


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_approval_fact_survives_model_denial_and_next_run(tmp_path: Path, decision: str):
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("fake")
    access = AccessSession(work)
    registry = ToolRegistry()
    registry.register(RequestFileAccessTool(access, registry))
    adapter = FakeModelAdapter(
        [
            tool_turn(
                "request_file_access",
                {
                    "path": str(outside),
                    "mode": "read",
                    "scope": "session",
                    "reason": "test",
                },
            ),
            ModelTurn(finish_reason="stop", assistant_text="审批从未发生。"),
            ModelTurn(finish_reason="stop", assistant_text="查看历史。"),
        ]
    )
    runtime = VeraRuntime(adapter, registry, tmp_path / "state", access_session=access)
    events = list(runtime.handle(StartRun(goal="授权", workspace_root=work, model_profile="fake")))
    required = next(event for event in events if event.type == "approval.required")
    events.extend(
        runtime.handle(
            ResolveApproval(
                run_id=required.run_id,
                approval_id=required.payload["approval_id"],
                target_hash=required.payload["target_hash"],
                decision=decision,
            )
        )
    )
    message = next(item for item in adapter.requests[1].messages if item.role == "tool")
    payload = json.loads(message.content)
    assert payload["core_approval"]["decision"] == decision
    assert payload["core_approval"]["approval_id"] == required.payload["approval_id"]
    assert payload["ok"] == (decision == "approve")
    conversation = ConversationContext(100_000)
    conversation.record_run("授权", events)
    # Model denial remains visible, but cannot erase Core evidence in the same history.
    list(
        runtime.handle(
            StartRun(
                goal="此前审批是否发生",
                workspace_root=work,
                model_profile="fake",
                conversation=conversation.snapshot(),
            )
        )
    )
    history = "\n".join(item.content for item in adapter.requests[-1].messages)
    assert required.payload["approval_id"] in history
    assert "approval.resolved" in history
    assert "tool.completed" in history
    assert decision in history
    if decision == "approve":
        assert access.grants()[0].grant_id in history
    else:
        assert "approval_rejected" in history
        assert not access.grants()
    # Persisted evidence survives reload and compaction, but no permission is restored.
    store = ConversationSessionStore(tmp_path / "sessions", "install-test", Redactor([]))
    created = store.create(work)
    store.append_turn(created.session_id, ConversationTurnProjector().from_run("授权", events))
    loaded = store.load(created.session_id, work)
    restored = ConversationContext.restore(
        100_000,
        session_id=loaded.session_id,
        messages=loaded.model_messages,
        compaction_count=0,
    )
    restored.replace_with_summary("简要摘要 [facts]：模型没有保留审批详情。")
    assert required.payload["approval_id"] in restored.snapshot()[0].content
    fresh_access = AccessSession(work)
    fresh_registry = ToolRegistry()
    fresh_registry.register(ReadTool(PermissionPaths(fresh_access), 1000))
    fresh_adapter = FakeModelAdapter(
        [
            tool_turn("read", {"path": str(outside)}),
            ModelTurn(finish_reason="stop", assistant_text="需要新的授权。"),
        ]
    )
    fresh = VeraRuntime(
        fresh_adapter, fresh_registry, tmp_path / "fresh", access_session=fresh_access
    )
    list(
        fresh.handle(
            StartRun(
                goal="读取外部文件",
                workspace_root=work,
                model_profile="fake",
                conversation=restored.snapshot(),
            )
        )
    )
    assert not fresh_access.grants()
    rejected = next(
        message for message in fresh_adapter.requests[-1].messages if message.role == "tool"
    )
    assert "file_access_approval_required" in rejected.content
    # The real session compaction flow must persist the enriched summary, not just display it.
    host = SimpleNamespace(
        conversation=restored,
        session_store=store,
        _last_saved_sequence=loaded.records[-1].sequence,
        _persistence_state="saved",
        _last_error_code=None,
        _session_event=lambda kind, payload: (kind, payload),
    )
    list(persist_compaction(host, "审批详情已省略。"))
    reloaded = store.load(created.session_id, work)
    persisted_history = "\n".join(message.content for message in reloaded.model_messages)
    assert required.payload["approval_id"] in persisted_history
    assert "approval.resolved" in persisted_history


@pytest.mark.parametrize(
    "text,limit", [("OUTSIDE_A_ONLY\n", 1000), ("中文\\n\n", 1000), ("abcdef", 3)]
)
def test_read_model_data_is_file_text_with_matching_metadata(tmp_path: Path, text: str, limit: int):
    (tmp_path / "inside.txt").write_text(text, encoding="utf-8")
    access = AccessSession(tmp_path)
    registry = ToolRegistry()
    registry.register(ReadTool(PermissionPaths(access), limit))
    adapter = FakeModelAdapter(
        [
            tool_turn("read", {"path": "inside.txt"}),
            ModelTurn(finish_reason="stop", assistant_text="读取完成。"),
        ]
    )
    runtime = VeraRuntime(adapter, registry, tmp_path / "state", access_session=access)
    list(runtime.handle(StartRun(goal="读取", workspace_root=tmp_path, model_profile="fake")))
    message = next(item for item in adapter.requests[-1].messages if item.role == "tool")
    payload = json.loads(message.content)
    expected = text.encode("utf-8")[:limit].decode("utf-8")
    assert payload["data"] == expected
    assert payload["data_format"] == "text"
    assert payload["byte_count"] == len(expected.encode("utf-8"))
    assert payload["content_hash"] == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert payload["truncated"] == (len(text.encode("utf-8")) > limit)
    assert payload["trust_level"] == "untrusted"
    assert "core_approval" not in payload


def test_history_facts_are_bounded_metadata_not_tool_body_or_model_claims():
    events = [
        EventEnvelope(
            event_id=f"event_{index}",
            run_id="run_test",
            sequence=index + 1,
            timestamp=datetime.now(UTC),
            type="tool.completed",
            payload={
                "name": "read",
                "call_id": f"call_{index}",
                "ok": True,
                "content": "PRIVATE_BODY",
                "unified_diff": "PRIVATE_DIFF",
                "target": "x" * 2000,
            },
        )
        for index in range(50)
    ]
    turn = ConversationTurnProjector().from_run("test", events)
    rows = [line for line in turn.assistant_text.splitlines() if line.startswith("[facts] {")]
    assert 0 < len(rows) <= 16
    assert len("\n".join(rows).encode()) <= 8000
    assert '"call_id":"call_49"' in rows[-1]
    assert "PRIVATE_BODY" not in turn.assistant_text
    assert "PRIVATE_DIFF" not in turn.assistant_text
    assert all(json.loads(row[8:])["historical_only"] for row in rows)

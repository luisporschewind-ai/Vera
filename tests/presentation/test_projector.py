from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame, StreamFrameType
from vera.presentation.projector import (
    AppendBlock,
    FocusBlock,
    TimelineProjector,
    UpdateBlock,
    project_user_prompt,
)
from vera.presentation.timeline import BlockKind, BlockStatus


def event(
    event_type: str,
    *,
    run_id: str = "run_1",
    sequence: int = 1,
    payload: dict | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"e{sequence}",
        run_id=run_id,
        sequence=sequence,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


def assistant_delta(stream_id: str, index: int, text: str) -> StreamFrame:
    return StreamFrame(
        run_id="run_1",
        stream_id=stream_id,
        index=index,
        type=StreamFrameType.ASSISTANT_DELTA,
        payload={"text": text},
    )


def only_appended_block(mutations):  # type: ignore[no-untyped-def]
    appends = [item.block for item in mutations if isinstance(item, AppendBlock)]
    assert len(appends) == 1
    return appends[0]


def test_expired_approval_is_expanded_error() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(event("approval.expired", payload={"expiry_reason": "facts_changed"}))
    )
    assert block.kind is BlockKind.ERROR
    assert block.expanded is True
    assert "过期" in block.body
    assert "重新生成" in block.body


def test_changeset_and_approval_are_expanded() -> None:
    projector = TimelineProjector()
    diff = only_appended_block(
        projector.apply(
            event(
                "changeset.proposed",
                payload={
                    "files": [{"path": "a.py", "unified_diff": "--- a/a.py\n+++ b/a.py\n+hi\n"}]
                },
            )
        )
    )
    approval_mutations = projector.apply(
        event("approval.required", sequence=2, payload={"approval_id": "a1", "risk": "low"})
    )
    approval = only_appended_block(approval_mutations)
    assert diff.kind is BlockKind.DIFF and diff.expanded is True
    assert approval.kind is BlockKind.APPROVAL and approval.expanded is True
    assert isinstance(approval_mutations[-1], FocusBlock)


def test_command_approval_shows_planned_argv_profile_and_root() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(
            event(
                "approval.required",
                payload={
                    "approval_id": "a-cmd",
                    "kind": "command",
                    "target_id": "verification_0",
                    "description": "执行验证命令",
                    "risk": "medium",
                    "argv": [
                        "xcodebuild",
                        "-project",
                        "Demo.xcodeproj",
                        "-scheme",
                        "Demo",
                        "build",
                        "-derivedDataPath",
                        "/private/tmp/vera-verification/abcd/run_1/000/DerivedData",
                    ],
                    "cwd": ".",
                    "artifact_profile": "xcode",
                    "artifact_root": "/private/tmp/vera-verification/abcd/run_1/000",
                },
            )
        )
    )
    assert block.kind is BlockKind.APPROVAL
    derived = "-derivedDataPath /private/tmp/vera-verification/abcd/run_1/000/DerivedData"
    assert derived in block.body
    assert "验证配置：xcode" in block.body
    assert "产物根目录：/private/tmp/vera-verification/abcd/run_1/000" in block.body
    assert "verification_0" not in block.body


def test_tool_approval_shows_only_core_provided_permission_scopes() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(
            event(
                "approval.required",
                payload={
                    "approval_id": "a-tool",
                    "kind": "tool",
                    "risk": "high",
                    "available_scopes": ["once", "run"],
                    "description": "执行命令",
                },
            )
        )
    )

    assert "授权范围 once, run" in block.body
    assert "workspace" not in block.body


def test_apple_service_approval_shows_exact_scope_inheritance_and_risk() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(
            event(
                "approval.required",
                payload={
                    "approval_id": "a-apple",
                    "kind": "tool",
                    "risk": "high",
                    "available_scopes": ["once"],
                    "description": "Apple 构建系统服务已请求。",
                    "system_service_grant": {
                        "capability": "apple_ios_build_services",
                        "scope": "once",
                        "services": ["com.apple.CoreSimulator.CoreSimulatorService"],
                        "inherited_by_descendants": True,
                        "may_access_current_user_simulator_state": True,
                    },
                },
            )
        )
    )

    assert "仅本次" in block.body
    assert "后代继承" in block.body
    assert "com.apple.CoreSimulator.CoreSimulatorService" in block.body
    assert "当前用户的模拟器状态" in block.body


def test_session_diff_is_a_diff_block() -> None:
    projector = TimelineProjector()
    filled = only_appended_block(
        projector.apply(
            event(
                "session.diff",
                payload={
                    "files": [{"path": "notes.md", "unified_diff": "--- a\n+++ b\n+hello\n"}],
                    "text": "notes.md\n--- a\n+++ b\n+hello\n",
                },
            )
        )
    )
    assert filled.kind is BlockKind.DIFF
    assert filled.expanded is True
    assert "notes.md" in filled.body
    assert "hello" in filled.body
    assert "文件数" not in filled.body
    empty = only_appended_block(
        projector.apply(
            event(
                "session.diff",
                sequence=2,
                payload={"files": [], "text": "没有 Diff。"},
            )
        )
    )
    assert empty.kind is BlockKind.DIFF
    assert empty.title == "Diff"
    assert empty.body == "没有 Diff。"


def test_duplicate_delta_is_ignored() -> None:
    projector = TimelineProjector()
    frame = assistant_delta(stream_id="s1", index=0, text="你")
    first = projector.apply(frame)
    second = projector.apply(frame)
    assert first
    assert second == ()


def test_gap_marks_incomplete_and_stops_deltas() -> None:
    projector = TimelineProjector()
    projector.apply(assistant_delta("s1", 0, "a"))
    gap = projector.apply(assistant_delta("s1", 2, "c"))
    assert gap and isinstance(gap[0], UpdateBlock)
    assert gap[0].block.incomplete is True
    assert projector.apply(assistant_delta("s1", 3, "d")) == () or gap[0].block.incomplete


def test_user_prompt_becomes_visible_user_block() -> None:
    projector = TimelineProjector()
    prompt = event("session.user_prompt", payload={"text": "你好vera"})
    block = only_appended_block(projector.apply(prompt))
    assert block.kind is BlockKind.USER
    assert block.title == "用户"
    assert block.body == "你好vera"
    assert block.expanded is True
    assert block.occurred_at == prompt.timestamp
    assert block.created_at == prompt.timestamp
    assert "session.user_prompt" not in block.title
    assert project_user_prompt("run_1", "你好vera").kind is BlockKind.USER


def test_list_directory_summary_has_target_and_body() -> None:
    projector = TimelineProjector()
    started = only_appended_block(
        projector.apply(
            event(
                "tool.started",
                payload={"name": "list_directory", "call_id": "c1", "target": "."},
            )
        )
    )
    assert started.kind is BlockKind.TOOL
    assert "列目录 1 次" in started.title
    assert "正在处理：." in started.body
    assert started.body != ""
    completed = projector.apply(
        event(
            "tool.completed",
            sequence=2,
            payload={
                "name": "list_directory",
                "call_id": "c1",
                "target": ".",
                "ok": True,
                "truncated": False,
            },
        )
    )
    assert isinstance(completed[0], UpdateBlock)
    block = completed[0].block
    assert "列目录 1 次" in block.title
    assert " · . · " in block.body
    assert "成功" in block.body
    assert block.body != ""
    assert "list_directory" not in block.title
    assert "tool.completed" not in block.title
    assert "tool.completed" not in block.body
    assert started.status is BlockStatus.RUNNING


def test_empty_user_prompt_is_omitted() -> None:
    projector = TimelineProjector()
    assert projector.apply(event("session.user_prompt", payload={"text": "   "})) == ()


def test_duplicate_status_is_omitted() -> None:
    projector = TimelineProjector()
    payload = {"checkpoint_id": "c1"}
    first = projector.apply(event("checkpoint.created", payload=payload))
    second = projector.apply(event("checkpoint.created", sequence=2, payload=payload))
    assert first
    assert second == ()


def test_tool_failure_expands_existing_block() -> None:
    projector = TimelineProjector()
    started = only_appended_block(
        projector.apply(event("tool.started", payload={"name": "read_file", "call_id": "c1"}))
    )
    assert started.expanded is False
    updated = projector.apply(
        event(
            "tool.completed",
            sequence=2,
            payload={"name": "read_file", "call_id": "c1", "ok": False, "error": "boom"},
        )
    )
    assert isinstance(updated[0], UpdateBlock)
    assert updated[0].block.expanded is True
    assert updated[0].block.status.value == "failed"


def test_assistant_message_replaces_stream_body() -> None:
    projector = TimelineProjector()
    projector.apply(assistant_delta("s1", 0, "partial"))
    mutations = projector.apply(
        event(
            "assistant.message",
            sequence=2,
            payload={"content": "final text", "stream_id": "s1"},
        )
    )
    assert isinstance(mutations[0], UpdateBlock)
    assert mutations[0].block.body == "final text"
    assert mutations[0].block.incomplete is False
    assert mutations[0].block.title == "Vera"


def test_projector_bounds_large_output_and_keeps_diff_approval() -> None:
    projector = TimelineProjector(max_body_bytes=64, max_blocks=8)
    huge = "line\n" * 10_000
    projector.apply(
        event(
            "changeset.proposed",
            payload={
                "files": [{"path": "App.swift", "unified_diff": huge}],
            },
        )
    )
    projector.apply(
        event("approval.required", sequence=2, payload={"approval_id": "a1", "risk": "low"})
    )
    projector.apply(event("run.failed", sequence=3, payload={"reason": "model_error"}))
    for index in range(20):
        projector.apply(
            event(
                "tool.completed",
                sequence=4 + index,
                payload={"name": "read_file", "result": huge, "ok": True},
            )
        )
    kinds = [block.kind for block in projector.blocks()]
    bodies = [block.body for block in projector.blocks()]
    assert BlockKind.DIFF in kinds
    assert BlockKind.APPROVAL in kinds
    assert BlockKind.ERROR in kinds
    assert all(len(body.encode("utf-8")) <= 64 for body in bodies)
    assert any(block.truncated for block in projector.blocks())
    assert len(projector.blocks()) <= 8


def test_session_status_is_startup_panel() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(
            event(
                "session.status",
                payload={
                    "version": "0.1.0",
                    "model_profile": "deepseek",
                    "model_name": "deepseek-flash",
                    "workspace": "/tmp/project",
                    "git": {"available": False, "branch": None, "dirty": None},
                    "context": {
                        "session_id": "session-1",
                        "message_count": 0,
                        "context_bytes": 0,
                        "max_bytes": 200_000,
                        "warning": False,
                        "compaction_count": 0,
                    },
                    "permissions": {
                        "approval_mode": "manual",
                        "changeset_approval": "required",
                        "command_policy": "allow/deny/approval-required",
                        "user_allowed_prefixes": [],
                        "execution_boundary": "current user",
                        "os_sandbox": False,
                    },
                },
            )
        )
    )
    assert block.kind is BlockKind.STATUS
    assert block.title == "会话状态"
    assert "Vera 0.1.0" in block.body
    assert "Model       deepseek / deepseek-flash" in block.body
    assert "Workspace" in block.body
    assert "文件数" not in block.body
    cleared = projector.apply(
        event(
            "session.message",
            sequence=2,
            payload={"clear_display": True, "text": "已开始新会话"},
        )
    )
    assert cleared == ()


def test_projector_reset_drops_blocks() -> None:
    projector = TimelineProjector()
    projector.apply(event("assistant.message", payload={"text": "旧回答"}))
    assert projector.blocks()
    projector.reset()
    assert projector.blocks() == ()


def test_recovery_detected_lists_run_id_and_next_commands() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(
            event(
                "recovery.detected",
                run_id="run_crash",
                payload={
                    "run_id": "run_crash",
                    "classification": "resumable_approval",
                    "stage": "awaiting_changeset_approval",
                    "reason_code": "awaiting_changeset_approval",
                    "allowed_actions": ["inspect", "resume", "abandon"],
                    "workspace_root": "/tmp/project",
                    "evidence": [{"path": "app.py", "state": "before"}],
                },
            )
        )
    )
    assert block.kind is BlockKind.STATUS
    assert block.status.value == "succeeded"
    assert block.title == "发现可恢复任务"
    assert "run-id：run_crash" in block.body
    assert "可续跑（等待审批）" in block.body
    assert "resumable_approval" in block.body
    assert "/resume run_crash" in block.body
    assert "/abandon run_crash" in block.body
    assert "原因未记录" not in block.body
    assert "恢复未完成" not in block.body
    assert "recovery.detected" not in block.title
    assert "recovery.detected" not in block.body


def test_recovery_manual_required_uses_reason_code() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(
            event(
                "recovery.manual_required",
                payload={"reason_code": "verification_in_flight"},
            )
        )
    )
    assert block.kind is BlockKind.ERROR
    assert "需要人工恢复" in block.title
    assert "不能自动处理 run_1" in block.body
    assert "验证进行中被中断" in block.body
    assert "verification_in_flight" in block.body
    assert "不允许 /resume 或 /abandon" in block.body
    assert "原因未记录" not in block.body


def test_permission_denied_marks_proposal_diff_unapplied() -> None:
    projector = TimelineProjector()
    projector.apply(
        event(
            "changeset.proposed",
            payload={
                "files": [{"path": "notes.md", "unified_diff": "--- a\n+++ b\n+hello\n"}],
            },
        )
    )
    mutations = projector.apply(
        event("run.failed", sequence=2, payload={"reason": "permission_denied"})
    )
    diff_update = next(item for item in mutations if isinstance(item, UpdateBlock))
    error = only_appended_block(mutations)
    assert diff_update.block.title == "Diff · 未写入"
    assert diff_update.block.status is BlockStatus.FAILED
    assert "没有写入权限" in error.body
    assert "未产生工作区变化" in error.body
    assert "已写入工作区变更" not in error.body


def test_applied_changeset_marks_proposal_diff_written() -> None:
    projector = TimelineProjector()
    projector.apply(
        event(
            "changeset.proposed",
            payload={
                "files": [{"path": "notes.md", "unified_diff": "--- a\n+++ b\n+hello\n"}],
            },
        )
    )
    mutations = projector.apply(
        event("changeset.applied", sequence=2, payload={"status": "applied"})
    )
    diff_update = next(item for item in mutations if isinstance(item, UpdateBlock))
    assert diff_update.block.title == "Diff · 已写入"
    assert diff_update.block.status is BlockStatus.SUCCEEDED


def test_project_instruction_status_hides_body() -> None:
    projector = TimelineProjector()
    block = only_appended_block(
        projector.apply(
            event(
                "project.instructions.status",
                payload={
                    "guidance_hash": "a" * 64,
                    "sources": [
                        {
                            "name": "AGENTS.md",
                            "priority": 10,
                            "content_hash": "b" * 64,
                            "byte_count": 12,
                        }
                    ],
                    "issues": [],
                    "text": "已加载 AGENTS.md 优先级 10 bbbbbbbbbbbb 12 bytes",
                },
            )
        )
    )
    assert "已加载" in block.body
    assert "AGENTS.md" in block.body
    assert "secret-body" not in block.body
    assert block.title == "项目指令"


def test_session_diff_unapplied_keeps_proposal_label() -> None:
    block = only_appended_block(
        TimelineProjector().apply(
            event(
                "session.diff",
                payload={
                    "files": [{"path": "notes.md", "unified_diff": "--- a\n+++ b\n+hello\n"}],
                    "applied": False,
                    "text": "这是提案 Diff，未写入工作区。\n\nnotes.md\n--- a\n+++ b\n+hello\n",
                },
            )
        )
    )
    assert "未写入" in block.title
    assert "未写入工作区" in block.body
    assert block.status is BlockStatus.FAILED

from pathlib import Path

import pytest
from pydantic import ValidationError

from vera.presentation.activity import ActivityState
from vera.presentation.footer_status import project_footer_status, render_footer_status
from vera.session.models import (
    ConversationStats,
    GitStatus,
    PermissionStatus,
    ReasoningStatus,
    SessionStatus,
)


def _status(
    *,
    used: int = 0,
    maximum: int = 100,
    warning: bool = False,
    reasoning: ReasoningStatus | None = None,
    persist: str = "saved",
) -> SessionStatus:
    return SessionStatus(
        version="0.1.0",
        model_profile="deepseek",
        model_name="deepseek-chat",
        workspace=Path("/tmp/ws"),
        git=GitStatus(available=True, branch="main", dirty=False),
        context=ConversationStats(
            session_id="s1",
            message_count=1,
            context_bytes=used,
            max_bytes=maximum,
            warning=warning,
            compaction_count=0,
            persistent_state=persist,  # type: ignore[arg-type]
        ),
        permissions=PermissionStatus(
            approval_mode="manual",
            changeset_approval="required",
            command_policy="allow",
            user_allowed_prefixes=(),
            execution_boundary="current user",
            os_sandbox=False,
        ),
        reasoning=reasoning or ReasoningStatus(mode="unavailable"),
    )


def test_context_percent_bounds() -> None:
    idle = ActivityState("就绪", "idle", False)
    empty = project_footer_status(_status(used=0), idle)
    assert empty.context_percent == 0
    assert "0%" in render_footer_status(empty, columns=80, unicode=True, frame="·")
    mid = project_footer_status(_status(used=24, maximum=100), idle)
    assert mid.context_percent == 24
    full = project_footer_status(_status(used=100, maximum=100, warning=True), idle)
    assert full.context_percent == 100
    assert full.context_warning is True


def test_reasoning_modes() -> None:
    idle = ActivityState("就绪", "idle", False)
    explicit = project_footer_status(
        _status(reasoning=ReasoningStatus(mode="explicit", effort="high")), idle
    )
    assert explicit.reasoning_label == "high"
    default = project_footer_status(
        _status(reasoning=ReasoningStatus(mode="provider_default")), idle
    )
    assert default.reasoning_label == "模型默认"
    missing = project_footer_status(_status(), idle)
    assert missing.reasoning_label == "不可用"


def test_explicit_requires_effort() -> None:
    with pytest.raises(ValidationError):
        ReasoningStatus(mode="explicit")
    with pytest.raises(ValidationError):
        ReasoningStatus(mode="unavailable", effort="high")


def test_wide_footer_has_both_sides() -> None:
    idle = ActivityState("就绪", "idle", False)
    footer = project_footer_status(_status(used=24, maximum=100), idle)
    text = render_footer_status(footer, columns=80, unicode=True, frame="·")
    assert "会话上下文" in text
    assert "24%" in text
    assert "deepseek-chat" in text
    assert "推理 不可用" in text
    assert "就绪" in text


def test_narrow_footer_keeps_percent_drops_model() -> None:
    idle = ActivityState("就绪", "idle", False)
    footer = project_footer_status(_status(used=24, maximum=100), idle)
    text = render_footer_status(footer, columns=60, unicode=True, frame="·")
    assert "24%" in text
    assert "deepseek-chat" not in text
    assert "推理" in text


def test_unsaved_persist_label() -> None:
    idle = ActivityState("就绪", "idle", False)
    footer = project_footer_status(_status(persist="unsaved"), idle)
    text = render_footer_status(footer, columns=80, unicode=True, frame="·")
    assert "未保存" in text


def test_activity_states_keep_words() -> None:
    for label, phase, active, severity in (
        ("正在思考", "thinking", True, "info"),
        ("等待审批", "approval", True, "warning"),
        ("正在验证", "verify", True, "info"),
        ("已完成", "done", False, "info"),
        ("已取消", "cancelled", False, "warning"),
        ("失败", "failed", False, "error"),
        ("正在恢复", "recovery", True, "warning"),
        ("未保存", "idle", False, "info"),
    ):
        footer = project_footer_status(_status(), ActivityState(label, phase, active, severity))
        text = render_footer_status(footer, columns=80, unicode=False, frame="o")
        assert label in text
        if active:
            assert "取消" in text
        else:
            assert "Esc/Ctrl-C 取消" not in text

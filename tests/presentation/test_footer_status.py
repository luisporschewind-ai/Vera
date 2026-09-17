from pathlib import Path

import pytest
from pydantic import ValidationError

from vera.presentation.activity import ActivityState
from vera.presentation.footer_status import (
    format_context_k,
    project_footer_status,
    render_footer_status,
)
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


def test_format_context_k() -> None:
    assert format_context_k(0) == "0"
    assert format_context_k(50) == "50"
    assert format_context_k(999) == "999"
    assert format_context_k(1000) == "1K"
    assert format_context_k(5368) == "5.4K"
    assert format_context_k(200_000) == "200K"


def test_context_percent_bounds() -> None:
    idle = ActivityState("就绪", "idle", False)
    empty = project_footer_status(_status(used=0), idle)
    assert empty.context_percent == 0
    assert "0/100" in render_footer_status(empty, columns=80, unicode=True, frame="·")
    mid = project_footer_status(_status(used=24, maximum=100), idle)
    assert mid.context_percent == 24
    assert "24/100" in render_footer_status(mid, columns=80, unicode=True, frame="·")
    full = project_footer_status(_status(used=100, maximum=100, warning=True), idle)
    assert full.context_percent == 100
    assert full.context_warning is True


def test_small_session_budget_is_not_shown_as_zero() -> None:
    idle = ActivityState("就绪", "idle", False)
    tiny = project_footer_status(_status(used=50, maximum=200_000), idle)
    assert tiny.context_percent == 0
    text = render_footer_status(tiny, columns=80, unicode=True, frame="·")
    assert "50/200K" in text
    assert "200000" not in text
    assert " 0%" not in text
    assert "█" in text


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
    assert "24/100" in text
    assert "就绪" not in text
    assert "deepseek-chat" in text
    assert "推理 不可用" in text
    assert "main" in text
    assert "审批 manual" in text
    assert "非 Git" not in text


def test_narrow_footer_keeps_model_name() -> None:
    idle = ActivityState("就绪", "idle", False)
    footer = project_footer_status(_status(used=24, maximum=100), idle)
    text = render_footer_status(footer, columns=60, unicode=True, frame="·")
    assert "24/100" in text or "审批" in text
    assert "deepseek-chat" in text


def test_footer_omits_branch_when_missing() -> None:
    idle = ActivityState("就绪", "idle", False)
    status = _status()
    status = status.model_copy(update={"git": GitStatus(available=False, branch=None, dirty=None)})
    text = render_footer_status(
        project_footer_status(status, idle), columns=80, unicode=True, frame="·"
    )
    assert "非 Git" not in text
    assert "审批 manual" in text


def test_unsaved_persist_label() -> None:
    idle = ActivityState("就绪", "idle", False)
    footer = project_footer_status(_status(persist="unsaved"), idle)
    text = render_footer_status(footer, columns=80, unicode=True, frame="·")
    assert "未保存" in text


def test_footer_does_not_show_activity() -> None:
    footer = project_footer_status(_status(), ActivityState("正在思考", "thinking", True))
    text = render_footer_status(footer, columns=80, unicode=True, frame="·")
    assert "正在思考" not in text
    assert "Esc/Ctrl-C 取消" not in text
    assert "会话上下文" in text


def test_footer_keeps_occupancy_while_thinking() -> None:
    idle = ActivityState("正在思考", "thinking", True, "info")
    footer = project_footer_status(_status(used=50, maximum=200_000), idle)
    text = render_footer_status(footer, columns=80, unicode=True, frame="·")
    assert "50/200K" in text
    assert "正在思考" not in text
    assert "上下文" in text
    assert " 0%" not in text

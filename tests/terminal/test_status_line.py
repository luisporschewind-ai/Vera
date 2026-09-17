from vera.presentation.activity import ActivityState
from vera.terminal.display import display_width
from vera.terminal.widgets.status_line import VeraStatusLine


def rendered(line: VeraStatusLine) -> str:
    return str(line.render())


def test_idle_line_does_not_offer_cancel() -> None:
    line = VeraStatusLine()
    assert "取消" not in rendered(line)
    assert "正在思考" not in rendered(line)


def test_activity_does_not_appear_on_footer() -> None:
    line = VeraStatusLine()
    line.set_activity(ActivityState("正在思考", "thinking", True), "·")
    text = rendered(line)
    assert "正在思考" not in text
    assert "Esc/Ctrl-C 取消" not in text


def test_footer_shows_context_and_model_on_wide_line() -> None:
    from pathlib import Path

    from vera.session.models import (
        ConversationStats,
        GitStatus,
        PermissionStatus,
        ReasoningStatus,
        SessionStatus,
    )

    line = VeraStatusLine()
    status = SessionStatus(
        version="0.1.0",
        model_profile="fake",
        model_name="fake-model",
        workspace=Path("/tmp/ws"),
        git=GitStatus(available=False, branch=None, dirty=None),
        context=ConversationStats(
            session_id="s",
            message_count=0,
            context_bytes=24,
            max_bytes=100,
            warning=False,
            compaction_count=0,
        ),
        permissions=PermissionStatus(
            approval_mode="manual",
            changeset_approval="required",
            command_policy="allow",
            user_allowed_prefixes=(),
            execution_boundary="current user",
            os_sandbox=False,
        ),
        reasoning=ReasoningStatus(mode="provider_default"),
    )
    line.set_geometry(columns=80, unicode=True)
    line.apply_session(status, ActivityState("就绪", "idle", False))
    text = rendered(line)
    assert "会话上下文" in text
    assert "24/100" in text
    assert "就绪" not in text
    assert "fake-model" in text
    assert "模型默认" in text
    assert "推理" in text
    assert display_width(text) == 76
    line.set_geometry(columns=60, unicode=True)
    line.apply_session(status, ActivityState("就绪", "idle", False))
    narrow = rendered(line)
    assert "fake-model" in narrow


def test_footer_notice_does_not_clip_model_name() -> None:
    from pathlib import Path

    from vera.session.models import (
        ConversationStats,
        GitStatus,
        PermissionStatus,
        ReasoningStatus,
        SessionStatus,
    )

    line = VeraStatusLine()
    status = SessionStatus(
        version="0.1.0",
        model_profile="fake",
        model_name="deepseek-flash",
        workspace=Path("/tmp/ws"),
        git=GitStatus(available=False, branch=None, dirty=None),
        context=ConversationStats(
            session_id="s",
            message_count=0,
            context_bytes=0,
            max_bytes=100,
            warning=False,
            compaction_count=0,
        ),
        permissions=PermissionStatus(
            approval_mode="manual",
            changeset_approval="required",
            command_policy="allow",
            user_allowed_prefixes=(),
            execution_boundary="current user",
            os_sandbox=False,
        ),
        reasoning=ReasoningStatus(mode="provider_default"),
    )
    line.set_geometry(columns=80, unicode=True)
    line.apply_session(status, ActivityState("就绪", "idle", False))
    line.set_status("输入 /help 查看命令")
    text = rendered(line)
    assert "deepseek-flash" in text
    assert "推理" in text
    assert display_width(text) == 76


def test_pending_count_survives_activity_update() -> None:
    from pathlib import Path

    from vera.session.models import (
        ConversationStats,
        GitStatus,
        PermissionStatus,
        ReasoningStatus,
        SessionStatus,
    )

    line = VeraStatusLine()
    status = SessionStatus(
        version="0.1.0",
        model_profile="fake",
        model_name="fake-model",
        workspace=Path("/tmp/ws"),
        git=GitStatus(available=False, branch=None, dirty=None),
        context=ConversationStats(
            session_id="s",
            message_count=0,
            context_bytes=0,
            max_bytes=100,
            warning=False,
            compaction_count=0,
        ),
        permissions=PermissionStatus(
            approval_mode="manual",
            changeset_approval="required",
            command_policy="allow",
            user_allowed_prefixes=(),
            execution_boundary="current user",
            os_sandbox=False,
        ),
        reasoning=ReasoningStatus(mode="unavailable"),
    )
    line.set_geometry(columns=80, unicode=True)
    line.apply_session(status)
    line.set_pending(3)
    line.set_activity(ActivityState("正在思考", "thinking", True), "·")
    assert "3 条新消息" in rendered(line)
    assert "正在思考" not in rendered(line)

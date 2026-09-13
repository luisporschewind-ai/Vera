from vera.presentation.activity import ActivityState
from vera.terminal.widgets.status_line import VeraStatusLine


def rendered(line: VeraStatusLine) -> str:
    return str(line.render())


def test_idle_line_does_not_offer_cancel() -> None:
    line = VeraStatusLine()
    assert "取消" not in rendered(line)
    assert "/help" in rendered(line)


def test_active_run_offers_cancel() -> None:
    line = VeraStatusLine()
    line.set_activity(ActivityState("正在思考", "thinking", True), "·")
    text = rendered(line)
    assert "正在思考" in text
    assert "Esc/Ctrl-C 取消" in text


def test_terminal_states_do_not_offer_cancel() -> None:
    for label, severity in (("失败", "error"), ("已完成", "info"), ("已取消", "warning")):
        line = VeraStatusLine()
        line.set_activity(ActivityState(label, "done", False, severity), "·")
        text = rendered(line)
        assert label in text
        assert "取消" not in text.replace("已取消", "")


def test_pending_count_survives_activity_update() -> None:
    line = VeraStatusLine()
    line.set_pending(3)
    line.set_activity(ActivityState("正在思考", "thinking", True), "·")
    assert "3 条新消息" in rendered(line)

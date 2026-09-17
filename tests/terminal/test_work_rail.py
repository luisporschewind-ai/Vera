from vera.presentation.activity import ActivityState
from vera.terminal.widgets.work_rail import VeraWorkRail


def rendered(rail: VeraWorkRail) -> str:
    return str(rail.render())


def test_idle_work_rail_is_hidden() -> None:
    rail = VeraWorkRail()
    rail.set_activity(ActivityState("就绪", "idle", False), "·")
    assert rail.display is False
    assert rendered(rail) == ""


def test_active_work_rail_offers_cancel() -> None:
    rail = VeraWorkRail()
    rail.set_geometry(columns=80, unicode=True)
    rail.set_activity(ActivityState("正在思考", "thinking", True), "·")
    text = rendered(rail)
    assert rail.display is True
    assert "正在思考" in text
    assert "Esc/Ctrl-C 取消" in text

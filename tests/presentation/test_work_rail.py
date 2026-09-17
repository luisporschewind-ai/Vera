from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.activity import ActivityPresenter, ActivityState
from vera.presentation.work_rail import project_work_rail, render_work_rail


def event(event_type: str, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id="e1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


def test_work_rail_hides_when_idle() -> None:
    rail = project_work_rail(ActivityState("就绪", "idle", False))
    assert rail.visible is False
    assert render_work_rail(rail, columns=80, unicode=True, frame="·") == ""


def test_work_rail_hides_when_completed() -> None:
    rail = project_work_rail(ActivityState("已完成", "done", False))
    assert rail.visible is False


def test_work_rail_shows_thinking_and_cancel() -> None:
    rail = project_work_rail(ActivityState("正在思考", "thinking", True))
    text = render_work_rail(rail, columns=80, unicode=True, frame="·")
    assert "正在思考" in text
    assert "Esc/Ctrl-C 取消" in text
    assert "会话上下文" not in text


def test_work_rail_tracks_tool_target_and_steps() -> None:
    presenter = ActivityPresenter()
    presenter.apply(event("run.started"))
    presenter.apply(event("tool.started", {"name": "read_file", "target": "README.md"}))
    presenter.apply(event("tool.started", {"name": "search_text", "query": "webstats"}))
    state = presenter.apply(
        event("tool.started", {"name": "propose_changeset", "target": "webstats.py"})
    )
    assert state.label == "正在规划修改"
    assert state.target == "webstats.py"
    assert state.steps == ("读取", "搜索", "提出变更")
    text = render_work_rail(project_work_rail(state), columns=80, unicode=True, frame="·")
    assert "webstats.py" in text
    assert "读取 → 搜索 → 提出变更" in text


def test_work_rail_narrow_is_one_line() -> None:
    state = ActivityState("正在读取", "tool", True, target="README.md", steps=("读取",))
    text = render_work_rail(project_work_rail(state), columns=60, unicode=True, frame="·")
    assert "\n" not in text
    assert "正在读取" in text
    assert "README.md" in text


def test_failed_work_rail_stays_visible() -> None:
    rail = project_work_rail(ActivityState("失败", "failed", False, "error"))
    assert rail.visible is True
    text = render_work_rail(rail, columns=80, unicode=True, frame="·")
    assert "失败" in text
    assert "Esc/Ctrl-C 取消" not in text

from tests.cli.test_presenter import event
from vera.cli_presenter import HumanPresenter
from vera.presentation.projector import TimelineProjector
from vera.presentation.timeline import BlockKind


def read_events():
    for i in range(4):
        yield event(
            "tool.started", {"name": "read", "call_id": str(i), "target": f"{i}.txt"}, i * 4 + 1
        )
        yield event("tool.policy_decided", {"decision": "allow"}, i * 4 + 2)
        yield event("tool.action_prepared", {}, i * 4 + 3)
        yield event(
            "tool.completed",
            {"name": "read", "call_id": str(i), "target": f"{i}.txt", "ok": True},
            i * 4 + 4,
        )


def test_plain_summarizes_reads_and_retains_details() -> None:
    lines = []
    presenter = HumanPresenter(lines.append)
    presenter.write_events(tuple(read_events()))
    presenter.write_events((event("assistant.message", {"content": "done"}, 30),))
    text = "\n".join(lines)
    assert "状态更新" not in text
    assert "读取 4 次" in text
    assert len(lines) <= 4
    presenter.write_tool_details()
    assert all(f"{i}.txt" in "\n".join(lines) for i in range(4))
    assert "\x1b" not in "\n".join(lines)


def test_timeline_groups_reads_with_expandable_details() -> None:
    projector = TimelineProjector()
    for e in read_events():
        projector.apply(e)
    tools = [b for b in projector.blocks() if b.kind == BlockKind.TOOL]
    assert len(tools) == 1
    assert "读取 4 次" in tools[0].title
    assert all(f"{i}.txt" in tools[0].body for i in range(4))


def test_approval_and_failure_break_group_and_remain_visible() -> None:
    lines = []
    presenter = HumanPresenter(lines.append)
    events = list(read_events()) + [
        event(
            "approval.required",
            {"kind": "tool", "tool_name": "edit", "description": "DIFF_REQUIRED", "risk": "high"},
            20,
        ),
        event("approval.resolved", {"decision": "reject"}, 21),
        event(
            "tool.completed", {"name": "edit", "ok": False, "error_code": "approval_rejected"}, 22
        ),
    ]
    presenter.write_events(events)
    text = "\n".join(lines)
    assert text.index("读取 4 次") < text.index("DIFF_REQUIRED")
    assert "reject" in text and "失败" in text
    projector = TimelineProjector()
    for e in list(read_events()) + [
        event(
            "tool.completed",
            {
                "name": "read",
                "call_id": "4",
                "ok": False,
                "error_code": "permission_denied",
            },
            23,
        )
    ]:
        projector.apply(e)
    assert any(b.kind == BlockKind.ERROR for b in projector.blocks())

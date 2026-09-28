from pathlib import Path

import pytest
from rich.text import Text
from textual.app import App, ComposeResult

from vera.contracts.skills import SkillSummary


def test_picker_rows_group_and_disable_ambiguous_ids() -> None:
    from vera.terminal.widgets.skill_picker import build_skill_picker_rows

    items = (
        SkillSummary(
            source_kind="workspace",
            trust_level="untrusted",
            availability="available",
            skill_id="workspace:review",
            name="review",
            description="工程检查",
        ),
        SkillSummary(
            source_kind="user",
            trust_level="advisory",
            availability="conflict",
            skill_id="user:review",
            name="review",
            description="用户检查",
        ),
        SkillSummary(
            source_kind="user",
            trust_level="advisory",
            availability="conflict",
            skill_id="user:review",
            name="review",
            description="重复身份",
        ),
        SkillSummary(
            source_kind="builtin",
            trust_level="advisory",
            availability="invalid",
            reason_codes=("skill_manifest_invalid",),
        ),
    )
    rows = build_skill_picker_rows(items, selected_skill_id="workspace:review")

    assert [row.label for row in rows if row.kind == "heading"] == [
        "系统内置",
        "用户本地",
        "当前项目",
    ]
    assert all(not row.selectable for row in rows if row.skill_id == "user:review")
    assert any(row.skill_id == "workspace:review" and "待用" in row.label for row in rows)
    assert any("无效 Skill" in row.label for row in rows)


def test_picker_invalid_summary_has_safe_plain_label() -> None:
    from vera.terminal.widgets.skill_picker import build_skill_picker_rows

    item = SkillSummary(
        source_kind="workspace",
        trust_level="untrusted",
        availability="invalid",
        description="[red]\x1b[31m",
        reason_codes=("skill_manifest_invalid",),
    )
    rows = build_skill_picker_rows((item,), selected_skill_id=None)
    row = next(row for row in rows if row.kind == "skill")

    assert not row.selectable
    assert "无效 Skill" in row.label
    assert "skill_manifest_invalid" in row.label
    assert "\x1b" not in row.label
    assert Text(row.label).spans == []


def test_long_description_cannot_push_identity_out_of_narrow_picker() -> None:
    from vera.terminal.widgets.skill_picker import safe_skill_label

    item = SkillSummary(
        source_kind="user",
        trust_level="advisory",
        availability="conflict",
        skill_id="user:interview-term-brief",
        name="interview-term-brief",
        description="一段很长的描述" * 40,
    )
    label = safe_skill_label(item, selected_skill_id=None)

    assert "用户本地" in label[:60]
    assert "conflict" in label[:60]
    assert "user:interview-term-brief" in label[:80]
    assert label.index("user:interview-term-brief") < label.index("一段很长的描述")


@pytest.mark.asyncio
async def test_picker_skips_disabled_rows_and_sends_one_choice() -> None:
    from vera.terminal.widgets.skill_picker import SkillPicker, SkillPickerRow

    class PickerApp(App[None]):
        def __init__(self) -> None:
            super().__init__()
            self.chosen: list[str] = []

        def compose(self) -> ComposeResult:
            yield SkillPicker(id="skill-picker")

        def on_skill_picker_chosen(self, message: SkillPicker.Chosen) -> None:
            self.chosen.append(message.skill_id)

    app = PickerApp()
    async with app.run_test(size=(60, 16)) as pilot:
        picker = app.query_one(SkillPicker)
        picker.open(
            (
                SkillPickerRow(kind="heading", label="用户本地"),
                SkillPickerRow(kind="skill", label="first", skill_id="user:first", selectable=True),
                SkillPickerRow(
                    kind="skill", label="broken", skill_id="user:broken", selectable=False
                ),
                SkillPickerRow(
                    kind="skill", label="second", skill_id="user:second", selectable=True
                ),
            )
        )
        await pilot.pause()
        assert picker.display
        options = picker.query_one("#skill-picker-options")
        assert str(options.get_option_at_index(1).prompt).startswith("› ")
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        assert str(options.get_option_at_index(3).prompt).startswith("› ")
        assert not str(options.get_option_at_index(1).prompt).startswith("› ")
        assert app.chosen == ["user:second"]
        assert picker.pending_skill_id == "user:second"
        picker.reject("skill_not_found")
        assert picker.display
        assert picker.pending_skill_id is None
        assert "skill_not_found" in picker.error_text
        await pilot.press("escape")
        assert not picker.display


@pytest.mark.asyncio
async def test_picker_empty_list_cannot_choose() -> None:
    from vera.terminal.widgets.skill_picker import SkillPicker

    class PickerApp(App[None]):
        def compose(self) -> ComposeResult:
            yield SkillPicker(id="skill-picker")

    app = PickerApp()
    async with app.run_test(size=(60, 16)) as pilot:
        picker = app.query_one(SkillPicker)
        picker.open(())
        await pilot.pause()
        assert picker.display
        assert picker.pending_skill_id is None
        await pilot.press("enter", "escape")
        assert not picker.display


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(60, 16), (80, 24)])
async def test_picker_overlay_keeps_composer_visible_at_supported_sizes(
    size: tuple[int, int],
) -> None:
    from textual.widgets import Static

    from vera.terminal.theme import VERA_THEMES
    from vera.terminal.widgets.skill_picker import SkillPicker, SkillPickerRow

    class PickerApp(App[None]):
        CSS_PATH = str(Path(__file__).resolve().parents[2] / "src/vera/terminal/theme.tcss")

        def __init__(self) -> None:
            super().__init__()
            for theme in VERA_THEMES:
                self.register_theme(theme)
            self.theme = "default"

        def compose(self) -> ComposeResult:
            yield Static("timeline", id="timeline")
            yield SkillPicker(id="skill-picker")
            yield Static("composer", id="composer-bar")
            yield Static("status", id="status-line")

    app = PickerApp()
    async with app.run_test(size=size) as pilot:
        picker = app.query_one(SkillPicker)
        timeline = app.query_one("#timeline")
        before_height = timeline.region.height
        picker.open(
            (
                SkillPickerRow(kind="heading", label="用户本地"),
                SkillPickerRow(
                    kind="skill", label="review", skill_id="user:review", selectable=True
                ),
            )
        )
        await pilot.pause()
        composer = app.query_one("#composer-bar")
        assert picker.region.height >= 4
        assert picker.region.y + picker.region.height <= composer.region.y
        assert picker.query_one("#skill-picker-title").region.height >= 1
        assert timeline.region.height == before_height

"""Safe, grouped projection of public Skill summaries for the terminal picker."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from vera.contracts.skills import SkillSummary


@dataclass(frozen=True, slots=True)
class SkillPickerRow:
    kind: Literal["heading", "skill"]
    label: str
    skill_id: str | None = None
    selectable: bool = False


_SOURCES = (
    ("builtin", "系统内置"),
    ("user", "用户本地"),
    ("workspace", "当前项目"),
)


def _clean(value: str) -> str:
    return "".join(character for character in value if character.isprintable()).strip()


def safe_skill_label(item: SkillSummary, *, selected_skill_id: str | None) -> str:
    source_label = dict(_SOURCES)
    name = _clean(item.name or "") or "无效 Skill"
    description = _clean(item.description or "")
    marker = " [待用]" if item.skill_id and item.skill_id == selected_skill_id else ""
    identity = _clean(item.skill_id or "") if item.availability == "conflict" else ""
    reasons = ",".join(_clean(code) for code in item.reason_codes)
    detail = " · ".join(
        part
        for part in (
            source_label[item.source_kind],
            item.availability,
            identity,
            reasons,
            description[:40] + ("…" if len(description) > 40 else ""),
        )
        if part
    )
    return f"{name}{marker} — {detail}"


def build_skill_picker_rows(
    summaries: tuple[SkillSummary, ...], *, selected_skill_id: str | None
) -> tuple[SkillPickerRow, ...]:
    counts = Counter(item.skill_id for item in summaries if item.skill_id)
    rows: list[SkillPickerRow] = []
    for source, heading in _SOURCES:
        group = sorted(
            (item for item in summaries if item.source_kind == source),
            key=lambda item: (item.name is None, item.name or "", item.skill_id or ""),
        )
        if not group:
            continue
        rows.append(SkillPickerRow(kind="heading", label=heading))
        for item in group:
            selectable = bool(
                item.skill_id
                and item.name
                and counts[item.skill_id] == 1
                and item.availability in {"available", "conflict"}
            )
            rows.append(
                SkillPickerRow(
                    kind="skill",
                    label=safe_skill_label(item, selected_skill_id=selected_skill_id),
                    skill_id=item.skill_id,
                    selectable=selectable,
                )
            )
    return tuple(rows)


class SkillPicker(Vertical):
    """Keyboard-operated picker on the main Screen; it never changes Core state itself."""

    BINDINGS = [("escape", "escape", "Close")]

    class Chosen(Message):
        def __init__(self, skill_id: str) -> None:
            super().__init__()
            self.skill_id = skill_id

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.display = False
        self.pending_skill_id: str | None = None
        self.error_text = ""
        self._selectable_ids: set[str] = set()
        self._rows: tuple[SkillPickerRow, ...] = ()
        self._highlighted_index: int | None = None

    def compose(self) -> ComposeResult:
        yield Static("Skills · ↑↓ 选择 · Enter 确认 · Esc 返回", id="skill-picker-title")
        yield OptionList(id="skill-picker-options")
        yield Static("", id="skill-picker-message")

    def open(self, rows: tuple[SkillPickerRow, ...]) -> None:
        options = self.query_one(OptionList)
        options.clear_options()
        self._rows = rows
        self._highlighted_index = None
        self._selectable_ids = {
            row.skill_id for row in rows if row.selectable and row.skill_id is not None
        }
        options.add_options(
            [
                Option(
                    Text(f"  {row.label}"),
                    id=row.skill_id if row.selectable else None,
                    disabled=not row.selectable,
                )
                for row in rows
            ]
        )
        self.pending_skill_id = None
        self.error_text = ""
        self.query_one("#skill-picker-message", Static).update(
            "" if rows else "三个来源均未发现可列出的 Skill"
        )
        self.display = True
        for index, row in enumerate(rows):
            if row.selectable:
                options.highlighted = index
                break
        options.focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if not self.display or event.option_index >= len(self._rows):
            return
        options = self.query_one(OptionList)
        previous = self._highlighted_index
        if previous is not None and previous < len(self._rows):
            options.replace_option_prompt_at_index(
                previous, Text(f"  {self._rows[previous].label}")
            )
        current = event.option_index
        options.replace_option_prompt_at_index(current, Text(f"› {self._rows[current].label}"))
        self._highlighted_index = current

    def close(self) -> None:
        self.display = False
        self.pending_skill_id = None
        self.error_text = ""

    def reject(self, code: str) -> None:
        self.pending_skill_id = None
        self.error_text = _clean(code) or "skill_selection_failed"
        self.query_one("#skill-picker-message", Static).update(
            f"选择失败：{self.error_text} · Esc 返回"
        )
        self.query_one(OptionList).focus()

    def action_escape(self) -> None:
        if self.pending_skill_id is None:
            self.close()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        skill_id = str(event.option.id) if event.option.id else None
        if (
            not self.display
            or self.pending_skill_id is not None
            or skill_id is None
            or skill_id not in self._selectable_ids
        ):
            return
        self.pending_skill_id = skill_id
        self.post_message(self.Chosen(skill_id))

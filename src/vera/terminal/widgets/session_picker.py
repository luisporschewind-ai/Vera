"""TTY session picker. Does not write journals."""

from __future__ import annotations

from collections.abc import Sequence

from vera.persistence.session_store import ConversationSessionSummary

_SHORT_ID = 8
_TITLE_WIDE = 36
_TITLE_NARROW = 18


def format_picker_rows(
    summaries: Sequence[ConversationSessionSummary],
    *,
    columns: int,
    rows: int,
) -> tuple[str, ...]:
    narrow = columns < 80 or rows <= 16
    title_limit = _TITLE_NARROW if narrow else _TITLE_WIDE
    lines: list[str] = []
    for index, item in enumerate(summaries, start=1):
        ident = item.session_id[:_SHORT_ID] if narrow else item.session_id
        clipped = item.title[: title_limit - 1] + "…"
        title = item.title if len(item.title) <= title_limit else clipped
        marker = "" if item.recoverable else " [损坏]"
        lines.append(f"{index}. {ident}  {title}{marker}")
    return tuple(lines)


def pick_session_id(
    summaries: Sequence[ConversationSessionSummary],
    *,
    plain: bool = False,
) -> str | None:
    usable = tuple(item for item in summaries if item.recoverable)
    if not usable:
        return None
    if plain:
        return _plain_pick(usable)
    return _tui_pick(usable)


def _plain_pick(summaries: Sequence[ConversationSessionSummary]) -> str | None:
    rows = format_picker_rows(summaries, columns=80, rows=24)
    for line in rows:
        print(line)
    try:
        raw = input("选择会话编号：").strip()
    except EOFError:
        return None
    if not raw:
        return None
    try:
        index = int(raw)
    except ValueError:
        return None
    if index < 1 or index > len(summaries):
        return None
    return summaries[index - 1].session_id


def _tui_pick(summaries: Sequence[ConversationSessionSummary]) -> str | None:
    from textual.app import App, ComposeResult
    from textual.widgets import Label, OptionList
    from textual.widgets.option_list import Option

    class SessionPickerApp(App[str | None]):
        CSS = "OptionList { height: 1fr; }"

        def compose(self) -> ComposeResult:
            yield Label("选择要恢复的会话（Enter 确认，Esc 取消）")
            options = [
                Option(
                    f"{item.session_id[:_SHORT_ID]}  {item.title}",
                    id=item.session_id,
                    disabled=not item.recoverable,
                )
                for item in summaries
            ]
            yield OptionList(*options, id="session-options")

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            self.exit(str(event.option.id) if event.option.id else None)

        def key_escape(self) -> None:
            self.exit(None)

    return SessionPickerApp().run()

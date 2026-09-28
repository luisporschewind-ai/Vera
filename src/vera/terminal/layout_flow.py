"""Layout and chrome flows for the Vera terminal app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.control import Control
from textual.css.query import NoMatches
from textual.events import Resize
from textual.geometry import Size
from textual.widgets import Static

from vera.presentation.timeline import BlockKind
from vera.terminal.bridge import RuntimeOutputReceived
from vera.terminal.widgets.blocks import TimelineBlockWidget
from vera.terminal.widgets.composer import ComposerBar, PromptComposer, select_composer_prompt
from vera.terminal.widgets.header import VeraHeader
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.terminal.widgets.timeline import ConversationTimeline
from vera.terminal.widgets.user_sticky import UserStickyBar
from vera.terminal.widgets.welcome import VeraWelcome
from vera.terminal.widgets.work_rail import VeraWorkRail

if TYPE_CHECKING:
    from vera.terminal.app import VeraTerminalApp

_RESIZE_CLEAR = Control.clear().segment.text + Control.home().segment.text


def present_bootstrap(host: VeraTerminalApp) -> None:
    for event in host.controller.bootstrap_events():
        host.on_runtime_output_received(RuntimeOutputReceived(event))


def on_resize(host: VeraTerminalApp, event: Resize) -> None:
    host._apply_size(event.size)


def on_unmount(host: VeraTerminalApp) -> None:
    host.bridge.cancel_workers()


def unicode(host: VeraTerminalApp) -> bool:
    term = host.display_capabilities.term.strip().lower()
    return term not in {"", "dumb", "unavailable"}


def apply_size(host: VeraTerminalApp, size: Size) -> None:
    too_small = size.width < host.MINIMUM_SIZE.width or size.height < host.MINIMUM_SIZE.height
    try:
        banner = host.query_one("#terminal-too-small", Static)
        header = host.query_one(VeraHeader)
    except NoMatches:
        return
    banner.display = too_small
    header.set_expanded(host._welcome_expanded)
    header.apply_geometry(columns=size.width, rows=size.height, unicode=host._unicode())
    status = host._status_line()
    if status is not None:
        status.set_geometry(columns=size.width, unicode=host._unicode())
    rail = host._work_rail()
    if rail is not None:
        rail.set_geometry(columns=size.width, unicode=host._unicode())
    if host._session_status is not None:
        host._refresh_chrome()
    else:
        host._sync_sticky_offset()
    if not too_small:
        try:
            composer = host.query_one(PromptComposer)
        except NoMatches:
            composer = None
        if composer is not None:
            composer.focus()
    host.refresh(repaint=True, layout=True)
    host.call_after_refresh(host._repaint_after_resize)


def repaint_after_resize(host: VeraTerminalApp) -> None:
    if not host.is_running:
        return
    status = host._status_line()
    if status is not None:
        status.set_geometry(columns=host.size.width, unicode=host._unicode())
    try:
        composer = host.query_one(PromptComposer)
        composer.sync_multiline_layout()
        composer.refresh(repaint=True, layout=True)
        host.query_one(ComposerBar).refresh(repaint=True, layout=True)
    except NoMatches:
        pass
    try:
        header = host.query_one(VeraHeader)
        header.refresh(repaint=True, layout=True)
    except NoMatches:
        pass
    try:
        timeline = host.query_one(ConversationTimeline)
        timeline.refresh(repaint=True, layout=True)
        for widget in timeline.query(TimelineBlockWidget):
            if widget.block.kind in {BlockKind.ASSISTANT, BlockKind.DIFF}:
                widget._render_body()
                widget.refresh(repaint=True)
    except NoMatches:
        pass
    if host._driver is not None:
        host._driver.write(_RESIZE_CLEAR)
        host._driver.flush()
    host.screen.refresh(repaint=True)


def collapse_welcome(host: VeraTerminalApp) -> None:
    if not host._welcome_expanded:
        return
    host._welcome_expanded = False
    try:
        header = host.query_one(VeraHeader)
    except NoMatches:
        return
    header.set_wave_phase(None)
    header.set_expanded(False)
    if host._session_status is not None:
        header.set_session_status(host._session_status)


def status_line(host: VeraTerminalApp) -> VeraStatusLine | None:
    try:
        return host.query_one(VeraStatusLine)
    except NoMatches:
        return None


def work_rail(host: VeraTerminalApp) -> VeraWorkRail | None:
    try:
        return host.query_one(VeraWorkRail)
    except NoMatches:
        return None


def sync_activity(host: VeraTerminalApp) -> None:
    rail = host._work_rail()
    if rail is not None:
        rail.set_activity(host.activity.current, host.animation.frame())


def apply_theme(host: VeraTerminalApp, name: str) -> None:
    from vera.terminal.theme import THEME_NAMES, theme_class

    if name not in THEME_NAMES or name not in host.available_themes:
        return
    previous = host.theme
    host.theme = name
    if previous == name:
        host.refresh_css(animate=False)
    for item in THEME_NAMES:
        active = item == name
        host.set_class(active, theme_class(item))
        host.screen.set_class(active, theme_class(item))
    host.refresh_css(animate=False)
    host.refresh()
    host._sync_sticky_offset()


def sync_sticky_offset(host: VeraTerminalApp) -> None:
    try:
        sticky = host.query_one(UserStickyBar)
        bar = host.query_one(ComposerBar)
    except NoMatches:
        return
    columns = host.size.width
    rows = host.size.height
    unicode = host._unicode()
    sticky.styles.margin = (0, 2, 0, 2)
    sticky.apply_geometry(columns=columns, rows=rows, unicode=unicode)
    try:
        bar.set_prompt_glyph(select_composer_prompt(unicode=unicode))
    except NoMatches:
        return


def refresh_chrome(host: VeraTerminalApp) -> None:
    status = host._session_status
    if status is None:
        return
    try:
        header = host.query_one(VeraHeader)
        welcome = host.query_one(VeraWelcome)
    except NoMatches:
        return
    header.set_expanded(host._welcome_expanded)
    header.set_session_status(status)
    if host._welcome_expanded and host.animations:
        header.set_wave_phase(host.animation.wave_phase())
    else:
        header.set_wave_phase(None)
    mark = header.current_mark()
    welcome.set_content(mark, status, columns=host.size.width)
    host._sync_sticky_offset()
    line = host._status_line()
    if line is not None:
        line.apply_session(status, unread=line._pending)
    host._sync_activity()


def tick_status(host: VeraTerminalApp) -> None:
    if not host.is_running:
        return
    if host._session_status is not None:
        context = host.controller.conversation_stats()
        if context != host._session_status.context:
            host._session_status = host._session_status.model_copy(update={"context": context})
        host._refresh_chrome()
        if host.activity.current.active:
            host._sync_activity()
        return
    if not host.activity.current.active:
        return
    host._sync_activity()


def tick_wave(host: VeraTerminalApp) -> None:
    if not host.is_running or not host._welcome_expanded or not host.animations:
        return
    try:
        header = host.query_one(VeraHeader)
    except NoMatches:
        return
    header.set_wave_phase(host.animation.wave_phase())

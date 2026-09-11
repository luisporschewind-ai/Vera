"""Scrollable conversation timeline with structured blocks."""

from __future__ import annotations

from textual.containers import VerticalScroll

from vera.presentation.projector import (
    AppendBlock,
    FocusBlock,
    TimelineMutation,
    UpdateBlock,
)
from vera.presentation.timeline import TimelineBlock
from vera.terminal.render_scheduler import RenderScheduler
from vera.terminal.widgets.blocks import TimelineBlockWidget


class ConversationTimeline(VerticalScroll):
    """Apply TimelineMutation values without rebuilding the full DOM."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.follow_tail = True
        self.pending_update_count = 0
        self._widgets: dict[str, TimelineBlockWidget] = {}
        self._scheduler = RenderScheduler()
        self._user_scrolled_away = False

    def on_mount(self) -> None:
        self.can_focus = True

    def apply(self, mutations: tuple[TimelineMutation, ...] | list[TimelineMutation]) -> None:
        previous_y = self.scroll_y
        for mutation in mutations:
            if isinstance(mutation, AppendBlock):
                self._append(mutation.block)
            elif isinstance(mutation, UpdateBlock):
                self._update(mutation.block)
            elif isinstance(mutation, FocusBlock):
                widget = self._widgets.get(mutation.block_id)
                if widget is not None:
                    widget.focus()
        if self.follow_tail and not self._user_scrolled_away:
            self.scroll_end(animate=False)
        elif mutations:
            self.pending_update_count += 1
            self.scroll_to(y=previous_y, animate=False)

    def apply_streaming_update(self, block: TimelineBlock) -> None:
        should_flush = self._scheduler.submit(block.block_id, block)
        if should_flush:
            self.flush_scheduled()

    def flush_scheduled(self) -> None:
        pending = self._scheduler.flush()
        for value in pending.values():
            if isinstance(value, TimelineBlock):
                self._update(value)
        if self.follow_tail and not self._user_scrolled_away:
            self.scroll_end(animate=False)

    def return_to_tail(self) -> None:
        self.follow_tail = True
        self._user_scrolled_away = False
        self.pending_update_count = 0
        self.scroll_end(animate=False)

    def mark_user_scrolled(self) -> None:
        self.follow_tail = False
        self._user_scrolled_away = True

    def widget_count(self) -> int:
        return len(self._widgets)

    def block_widget(self, block_id: str) -> TimelineBlockWidget:
        return self._widgets[block_id]

    def on_mouse_scroll_up(self) -> None:
        self.mark_user_scrolled()

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key in {"pageup", "up"}:
            self.mark_user_scrolled()
        elif event.key == "end":
            self.return_to_tail()
            event.stop()

    def _append(self, block: TimelineBlock) -> None:
        if block.block_id in self._widgets:
            self._update(block)
            return
        widget = TimelineBlockWidget.from_model(block)
        self._widgets[block.block_id] = widget
        self.mount(widget)

    def _update(self, block: TimelineBlock) -> None:
        existing = self._widgets.get(block.block_id)
        if existing is None:
            self._append(block)
            return
        existing.apply_block(block)

"""Scrollable conversation timeline with structured blocks."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static

from vera.presentation.projector import (
    AppendBlock,
    FocusBlock,
    TimelineMutation,
    UpdateBlock,
)
from vera.presentation.timeline import BlockKind, TimelineBlock
from vera.terminal.streaming import bounded_scheduler
from vera.terminal.widgets.blocks import EventGroupWidget, TimelineBlockWidget
from vera.terminal.widgets.user_prompt_anchor import UserPromptAnchor

_GROUPED_KINDS = {BlockKind.TOOL, BlockKind.LOG, BlockKind.STATUS}


class ConversationTimeline(VerticalScroll):
    """Apply TimelineMutation values without rebuilding the full DOM."""

    DEFAULT_CSS = """
    ConversationTimeline {
        overflow-y: auto;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }
    """

    def __init__(self, *, id: str | None = None, paced: bool = True, unicode: bool = True) -> None:
        super().__init__(id=id)
        self._paced = paced
        self._unicode = unicode
        self.follow_tail = True
        self.pending_update_count = 0
        self._widgets: dict[str, TimelineBlockWidget] = {}
        self._scheduler = bounded_scheduler()
        self._user_scrolled_away = False
        self._tail_retries = 0
        self._kind_group: EventGroupWidget | None = None
        self._pending_reveal: set[str] = set()
        self._pending_outcome: dict[str, str] = {}
        self._outcomes: dict[str, Static] = {}
        self._reveal_timer_scheduled = False

    def on_mount(self) -> None:
        self.can_focus = True
        self.anchor()

    def clear_blocks(self) -> None:
        self._widgets.clear()
        self._kind_group = None
        self.pending_update_count = 0
        self.follow_tail = True
        self._user_scrolled_away = False
        self._tail_retries = 0
        self._scheduler = bounded_scheduler()
        self._pending_reveal.clear()
        self._pending_outcome.clear()
        self._outcomes.clear()
        self.remove_children()
        self.refresh_user_sticky()

    def pin_home(self) -> None:
        """Keep remaining blocks at the top after a display wipe."""
        self.follow_tail = False
        self._user_scrolled_away = False
        self.pending_update_count = 0
        self._tail_retries = 0
        if self.is_mounted:
            self.anchor(False)
            self.scroll_home(animate=False)
            self.call_after_refresh(self.refresh_user_sticky)

    def apply(self, mutations: tuple[TimelineMutation, ...] | list[TimelineMutation]) -> None:
        previous_y = self.scroll_y
        for mutation in mutations:
            if isinstance(mutation, AppendBlock):
                self._append(mutation.block)
            elif isinstance(mutation, UpdateBlock):
                self._update(mutation.block)
            elif isinstance(mutation, FocusBlock):
                widget = self._widgets.get(mutation.block_id)
                if widget is None:
                    continue
                from vera.terminal.widgets.approval import ApprovalBlockWidget

                if isinstance(widget, ApprovalBlockWidget):
                    widget.focus_default_action()
                    widget.scroll_visible(animate=False)
                else:
                    widget.focus()
        if self.follow_tail and not self._user_scrolled_away:
            self._request_tail_scroll()
        elif mutations:
            self.pending_update_count += 1
            self.scroll_to(y=previous_y, animate=False)
        self.call_after_refresh(self.refresh_user_sticky)

    def apply_streaming_update(self, block: TimelineBlock) -> None:
        should_flush = self._scheduler.submit(block.block_id, block)
        if should_flush:
            self.flush_scheduled()

    @property
    def has_pending_reveal(self) -> bool:
        return bool(self._pending_reveal)

    def queue_assistant(self, block: TimelineBlock) -> None:
        """Keep the full answer in the block and pace only its visible rows."""
        existing = self._widgets.get(block.block_id)
        previous_lines = existing.visible_line_count if existing is not None else 1
        if existing is None:
            self._append(block)
        else:
            self._update(block)
        widget = self._widgets[block.block_id]
        if not self._paced:
            widget.set_visible_lines(None)
            self._pending_reveal.discard(block.block_id)
            self._show_ready_outcomes()
            return
        widget.set_visible_lines(previous_lines)
        if widget.visible_line_count < widget.assistant_line_count:
            self._pending_reveal.add(block.block_id)
            self._schedule_reveal()
        else:
            widget.set_visible_lines(None)
            self._pending_reveal.discard(block.block_id)
            self._show_ready_outcomes()
        if self.follow_tail and not self._user_scrolled_away:
            self._request_tail_scroll()

    def advance_reveal(self) -> None:
        for block_id in tuple(self._pending_reveal):
            widget = self._widgets.get(block_id)
            if widget is None:
                self._pending_reveal.discard(block_id)
                continue
            remaining = widget.assistant_line_count - widget.visible_line_count
            if remaining <= 0:
                widget.set_visible_lines(None)
                self._pending_reveal.discard(block_id)
                continue
            step = max(1, (remaining + 19) // 20)
            widget.set_visible_lines(widget.visible_line_count + step)
            if widget.visible_line_count >= widget.assistant_line_count:
                widget.set_visible_lines(None)
                self._pending_reveal.discard(block_id)
        self._show_ready_outcomes()
        if self.follow_tail and not self._user_scrolled_away:
            self._request_tail_scroll()

    def finish_reveal(self) -> None:
        for block_id in self._pending_reveal:
            widget = self._widgets.get(block_id)
            if widget is not None:
                widget.set_visible_lines(None)
        self._pending_reveal.clear()
        self._show_ready_outcomes()

    def mark_outcome(self, run_id: str, outcome: str) -> None:
        self._pending_outcome[run_id] = outcome
        self._show_ready_outcomes()

    def _show_ready_outcomes(self) -> None:
        for run_id, outcome in tuple(self._pending_outcome.items()):
            if any(
                self._widgets.get(block_id) is not None
                and self._widgets[block_id].block.run_id == run_id
                for block_id in self._pending_reveal
            ):
                continue
            del self._pending_outcome[run_id]
            if run_id in self._outcomes:
                continue
            marker, label = {
                "done": ("✓" if self._unicode else "+", "Done"),
                "cancelled": ("×" if self._unicode else "x", "Cancelled"),
                "failed": ("!", "Failed"),
            }[outcome]
            row = Static(f"{marker} {label}", classes=f"run-outcome run-outcome-{outcome}")
            self._outcomes[run_id] = row
            self._kind_group = None
            self.mount(row)
            if self.follow_tail and not self._user_scrolled_away:
                self._request_tail_scroll()

    def _schedule_reveal(self) -> None:
        if self._reveal_timer_scheduled or not self.is_mounted:
            return
        self._reveal_timer_scheduled = True
        self.set_timer(0.06, self._tick_reveal)

    def _tick_reveal(self) -> None:
        self._reveal_timer_scheduled = False
        if not self._pending_reveal:
            return
        self.advance_reveal()
        if self._pending_reveal:
            self._schedule_reveal()

    def flush_scheduled(self) -> None:
        pending = self._scheduler.flush()
        for value in pending.values():
            if isinstance(value, TimelineBlock):
                self._update(value)
        if self.follow_tail and not self._user_scrolled_away:
            self._request_tail_scroll()
        self.call_after_refresh(self.refresh_user_sticky)

    def _request_tail_scroll(self) -> None:
        """Keep the tail pinned while content mounts or grows.

        A plain scroll_end here would measure the pre-growth height, so rely on
        Textual anchoring and re-check once layout has settled.
        """

        if not self.is_mounted:
            return
        self.anchor()
        self.call_after_refresh(self._scroll_to_tail)

    def _is_at_tail(self) -> bool:
        if not self.is_mounted:
            return False
        return self.max_scroll_y <= 0 or self.scroll_y >= self.max_scroll_y - 1

    def _scroll_to_tail(self) -> None:
        if not (self.follow_tail and not self._user_scrolled_away):
            self._tail_retries = 0
            return
        self.scroll_end(animate=False)
        if self.max_scroll_y > 0 and self.scroll_y < self.max_scroll_y and self._tail_retries < 8:
            self._tail_retries += 1
            self.call_after_refresh(self._scroll_to_tail)
            return
        self._tail_retries = 0
        self.refresh_user_sticky()

    def return_to_tail(self) -> None:
        self.follow_tail = True
        self._user_scrolled_away = False
        self.pending_update_count = 0
        self._tail_retries = 0
        self.scroll_end(animate=False)
        self._request_tail_scroll()

    def mark_user_scrolled(self) -> None:
        self.follow_tail = False
        self._user_scrolled_away = True
        if self.is_mounted:
            self.anchor(False)

    def _unpin_if_left_tail(self) -> None:
        if not self._is_at_tail():
            self.mark_user_scrolled()

    def widget_count(self) -> int:
        return len(self._widgets)

    def block_widget(self, block_id: str) -> TimelineBlockWidget:
        return self._widgets[block_id]

    def has_block(self, block_id: str) -> bool:
        return block_id in self._widgets

    def on_resize(self) -> None:
        if self.follow_tail and not self._user_scrolled_away:
            self._request_tail_scroll()
        self.call_after_refresh(self.refresh_user_sticky)

    def on_scroll(self, event=None) -> None:  # type: ignore[no-untyped-def]
        self.refresh_user_sticky()

    def on_mouse_scroll_up(self, event=None) -> None:  # type: ignore[no-untyped-def]
        self.call_after_refresh(self._unpin_if_left_tail)
        self.call_after_refresh(self.refresh_user_sticky)
        if event is not None:
            event.stop()

    def on_mouse_scroll_down(self, event=None) -> None:  # type: ignore[no-untyped-def]
        self.call_after_refresh(self.refresh_user_sticky)
        if event is not None:
            event.stop()

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key in {"pageup", "up"}:
            self.call_after_refresh(self._unpin_if_left_tail)
            self.call_after_refresh(self.refresh_user_sticky)
        elif event.key == "end":
            self.return_to_tail()
            event.stop()

    def refresh_user_sticky(self) -> None:
        if not self.is_attached:
            return
        try:
            bar = self.app.query_one("#user-sticky", UserPromptAnchor)
        except Exception:
            return
        widget = self.scrolled_off_user()
        if widget is None:
            bar.hide_message()
            return
        bar.show_block(widget.block)

    def scrolled_off_user(self) -> TimelineBlockWidget | None:
        """Last user message whose top has left the visible timeline."""

        if not self.is_mounted:
            return None
        visible_top = self.region.y
        last: TimelineBlockWidget | None = None
        for widget in self._widgets.values():
            if widget.block.kind is not BlockKind.USER or not widget.is_mounted:
                continue
            if widget.region.y < visible_top:
                last = widget
        return last

    def _append(self, block: TimelineBlock) -> None:
        if block.block_id in self._widgets:
            self._update(block)
            return
        widget = TimelineBlockWidget.from_model(block, approval_id=block.ref_id)
        self._widgets[block.block_id] = widget
        if block.kind in _GROUPED_KINDS:
            if self._kind_group is None or self._kind_group.kind is not block.kind:
                self._kind_group = EventGroupWidget(block.kind)
                self._kind_group.add_item(widget)
                self.mount(self._kind_group)
            else:
                self._kind_group.add_item(widget)
            return
        self._kind_group = None
        self.mount(widget)

    def _update(self, block: TimelineBlock) -> None:
        existing = self._widgets.get(block.block_id)
        if existing is None:
            self._append(block)
            return
        existing.apply_block(block)
        group = _owning_group(existing)
        if group is not None:
            group.refresh_heading()


def _owning_group(widget: TimelineBlockWidget) -> EventGroupWidget | None:
    node = widget.parent
    while node is not None:
        if isinstance(node, EventGroupWidget):
            return node
        node = node.parent
    return None

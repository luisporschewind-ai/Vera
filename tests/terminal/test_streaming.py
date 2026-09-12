from vera.terminal.widgets.timeline import ConversationTimeline


def test_streaming_update_does_not_reset_user_scroll_flag() -> None:
    timeline = ConversationTimeline()
    timeline.mark_user_scrolled()
    assert timeline.follow_tail is False
    timeline.flush_scheduled()
    assert timeline.follow_tail is False
    assert timeline._user_scrolled_away is True

from vera.terminal.widgets.timeline import ConversationTimeline


def test_timeline_keeps_anchor_when_user_leaves_tail() -> None:
    timeline = ConversationTimeline()
    timeline.mark_user_scrolled()
    assert timeline.follow_tail is False
    assert timeline._user_scrolled_away is True
    timeline.pending_update_count = 2
    timeline.return_to_tail()
    assert timeline.pending_update_count == 0
    assert timeline.follow_tail is True
    assert timeline._user_scrolled_away is False

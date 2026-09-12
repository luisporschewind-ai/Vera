from vera.session.history import PromptHistory


def test_history_navigates_and_restores_draft() -> None:
    history = PromptHistory()
    history.record("one")
    history.record("two")
    assert history.up("draft") == "two"
    assert history.up("draft") == "one"
    assert history.up("draft") == "one"
    assert history.down() == "two"
    assert history.down() == "draft"


def test_history_deduplicates_and_respects_limit() -> None:
    history = PromptHistory(limit=2)
    history.record("one")
    history.record("one")
    history.record("two")
    history.record("three")
    assert len(history) == 2
    assert history.up("") == "three"
    assert history.up("") == "two"


def test_history_search_and_clear_are_in_memory() -> None:
    history = PromptHistory()
    history.record("修复审批")
    history.record("hello 世界")
    assert history.search("世界") == ("hello 世界",)
    assert history.search("") == ()
    history.record("")
    history.clear()
    assert len(history) == 0
    assert history.up("x") == "x"
    assert history.browsing() is False

from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.terminal.disclosure import DisclosurePolicy as TerminalDisclosure


def test_default_disclosure_table() -> None:
    policy = DisclosurePolicy()
    assert TerminalDisclosure is DisclosurePolicy
    cases = {
        BlockKind.USER: True,
        BlockKind.ASSISTANT: True,
        BlockKind.TOOL: False,
        BlockKind.LOG: False,
        BlockKind.DIFF: True,
        BlockKind.APPROVAL: True,
        BlockKind.VERIFICATION: False,
        BlockKind.ERROR: True,
        BlockKind.STATUS: False,
    }
    for kind, expanded in cases.items():
        assert policy.initial_state(kind, BlockStatus.SUCCEEDED) is expanded
    assert policy.initial_state(BlockKind.TOOL, BlockStatus.FAILED) is True
    assert policy.initial_state(BlockKind.VERIFICATION, BlockStatus.FAILED) is True


def test_manual_toggle_is_sticky() -> None:
    policy = DisclosurePolicy()
    block = TimelineBlock(
        block_id="b1",
        run_id="run_1",
        kind=BlockKind.TOOL,
        title="tool",
        expanded=False,
    )
    toggled = policy.with_manual_toggle(block, True)
    updated = policy.on_status_change(toggled, BlockStatus.SUCCEEDED)
    assert updated.expanded is True
    assert updated.user_overridden is True

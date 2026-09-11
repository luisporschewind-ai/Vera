import pytest

from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock


@pytest.mark.parametrize(
    ("kind", "expanded"),
    [
        (BlockKind.TOOL, False),
        (BlockKind.LOG, False),
        (BlockKind.DIFF, True),
        (BlockKind.APPROVAL, True),
        (BlockKind.ERROR, True),
        (BlockKind.USER, True),
        (BlockKind.ASSISTANT, True),
        (BlockKind.STATUS, False),
    ],
)
def test_initial_disclosure(kind: BlockKind, expanded: bool) -> None:
    assert DisclosurePolicy().initial_state(kind, BlockStatus.PENDING) is expanded


def test_successful_verification_starts_collapsed() -> None:
    assert (
        DisclosurePolicy().initial_state(BlockKind.VERIFICATION, BlockStatus.SUCCEEDED) is False
    )


def test_failed_verification_starts_expanded() -> None:
    assert DisclosurePolicy().initial_state(BlockKind.VERIFICATION, BlockStatus.FAILED) is True


def test_failure_forces_expand_once_then_respects_user() -> None:
    policy = DisclosurePolicy()
    block = TimelineBlock(
        block_id="tool_1",
        run_id="run_1",
        kind=BlockKind.TOOL,
        title="read_file",
        status=BlockStatus.RUNNING,
        expanded=False,
    )
    failed = policy.on_status_change(block, BlockStatus.FAILED)
    assert failed.expanded is True
    collapsed = policy.with_manual_toggle(failed, False)
    assert collapsed.expanded is False
    assert collapsed.user_overridden is True
    still = policy.on_status_change(collapsed, BlockStatus.FAILED)
    assert still.expanded is False

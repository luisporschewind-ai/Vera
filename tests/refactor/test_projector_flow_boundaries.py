"""Import contracts for the extracted TimelineProjector flows."""

from vera.presentation.event_projector import EventProjector
from vera.presentation.mutations import AppendBlock, FocusBlock, TimelineMutation, UpdateBlock
from vera.presentation.prompt_block import project_user_prompt
from vera.presentation.stream_projector import StreamProjector
from vera.presentation.timeline_state import TimelineState


def test_projector_flow_facades_are_available() -> None:
    assert EventProjector is not None
    assert StreamProjector is not None
    assert TimelineState is not None
    assert callable(project_user_prompt)
    assert AppendBlock is not None
    assert UpdateBlock is not None
    assert FocusBlock is not None
    assert TimelineMutation is not None

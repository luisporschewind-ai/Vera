"""StreamFrame contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vera.contracts.streaming import StreamFrame, StreamFrameType, is_transient


def test_stream_frame_round_trips() -> None:
    frame = StreamFrame(
        run_id="run_1",
        stream_id="stream_1",
        index=0,
        type=StreamFrameType.ASSISTANT_DELTA,
        payload={"text": "你"},
    )
    assert StreamFrame.model_validate_json(frame.model_dump_json()) == frame
    assert is_transient(frame) is True


def test_assistant_delta_requires_non_empty_text() -> None:
    with pytest.raises(ValidationError):
        StreamFrame(
            run_id="run_1",
            stream_id="stream_1",
            index=0,
            type=StreamFrameType.ASSISTANT_DELTA,
            payload={"text": ""},
        )


def test_stream_frame_rejects_negative_index() -> None:
    with pytest.raises(ValidationError):
        StreamFrame(
            run_id="run_1",
            stream_id="stream_1",
            index=-1,
            type=StreamFrameType.ASSISTANT_DELTA,
            payload={"text": "x"},
        )

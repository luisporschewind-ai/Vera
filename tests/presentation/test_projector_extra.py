from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.projector import AppendBlock, TimelineProjector, UpdateBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock


def event(event_type: str, sequence: int = 1, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"e{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


def test_verification_success_collapses() -> None:
    projector = TimelineProjector()
    started = projector.apply(event("verification.started", payload={"argv": ["pytest"]}))
    assert isinstance(started[0], AppendBlock)
    done = projector.apply(
        event("verification.completed", sequence=2, payload={"status": "passed"})
    )
    assert isinstance(done[0], UpdateBlock)
    assert done[0].block.expanded is False
    assert done[0].block.status is BlockStatus.SUCCEEDED


def test_verification_failure_expands() -> None:
    projector = TimelineProjector()
    projector.apply(event("verification.started", payload={"argv": ["pytest"]}))
    done = projector.apply(
        event(
            "verification.completed",
            sequence=2,
            payload={"status": "failed", "stderr": "boom"},
        )
    )
    assert isinstance(done[0], UpdateBlock)
    assert done[0].block.expanded is True


def test_session_and_unknown_events() -> None:
    projector = TimelineProjector()
    msg = projector.apply(event("session.message", payload={"text": "hello"}))
    doctor = projector.apply(
        event(
            "session.doctor",
            sequence=2,
            payload={
                "items": [
                    {
                        "name": "python",
                        "status": "pass",
                        "detail": "3.12",
                    }
                ]
            },
        )
    )
    config = projector.apply(
        event(
            "session.config",
            sequence=3,
            payload={
                "sources": {"user": "absent", "project": "absent"},
                "providers": {
                    "fake": {
                        "model": "fake-model",
                        "base_url": "https://example.invalid",
                        "api_key_env": "FAKE_API_KEY",
                    }
                },
                "limits": {"max_tool_calls": 50},
                "editor_argv": [],
                "ui": {"theme": "default"},
            },
        )
    )
    unknown = projector.apply(event("custom.unknown", sequence=4, payload={"x": 1}))
    assert msg[0].block.kind is BlockKind.STATUS  # type: ignore[union-attr]
    assert msg[0].block.title == "会话"  # type: ignore[union-attr]
    assert msg[0].block.body == "hello"  # type: ignore[union-attr]
    assert doctor[0].block.title == "诊断"  # type: ignore[union-attr]
    assert doctor[0].block.body == "python  pass  3.12"  # type: ignore[union-attr]
    assert doctor[0].block.expanded is True  # type: ignore[union-attr]
    assert config[0].block.title == "配置"  # type: ignore[union-attr]
    assert "user  absent" in config[0].block.body  # type: ignore[union-attr]
    assert "fake  fake-model" in config[0].block.body  # type: ignore[union-attr]
    assert "sources: 2" not in config[0].block.body  # type: ignore[union-attr]
    assert unknown[0].block.kind is BlockKind.STATUS  # type: ignore[union-attr]
    assert unknown[0].block.title == "状态更新"  # type: ignore[union-attr]


def test_disclosure_verification_succeeded_path() -> None:
    policy = DisclosurePolicy()
    block = TimelineBlock(
        block_id="v1",
        run_id="run_1",
        kind=BlockKind.VERIFICATION,
        title="v",
        status=BlockStatus.RUNNING,
        expanded=True,
    )
    updated = policy.on_status_change(block, BlockStatus.SUCCEEDED)
    assert updated.expanded is False

"""ContractCodec version registry tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.codec import CommandType, ContractCodec, ContractVersionError
from vera.contracts.commands import (
    AbandonRun,
    CancelRun,
    InspectRecovery,
    ResolveApproval,
    ResumeRun,
    RollbackRun,
    StartRun,
)
from vera.contracts.events import EventEnvelope


@pytest.mark.parametrize(
    ("command_type", "command"),
    [
        (
            CommandType.START_RUN,
            StartRun(
                goal="demo",
                workspace_root=Path("/tmp/ws"),
                model_profile="default",
            ),
        ),
        (
            CommandType.RESOLVE_APPROVAL,
            ResolveApproval(
                run_id="run_1",
                approval_id="apr_1",
                target_hash="abc",
                decision="approve",
            ),
        ),
        (CommandType.CANCEL_RUN, CancelRun(run_id="run_1")),
        (CommandType.ROLLBACK_RUN, RollbackRun(run_id="run_1")),
        (CommandType.INSPECT_RECOVERY, InspectRecovery(run_id="run_1")),
        (CommandType.RESUME_RUN, ResumeRun(run_id="run_1")),
        (CommandType.ABANDON_RUN, AbandonRun(run_id="run_1")),
    ],
)
def test_command_codec_round_trips_each_type(command_type: CommandType, command: object) -> None:
    codec = ContractCodec()
    encoded = codec.encode_command(command)  # type: ignore[arg-type]
    assert codec.decode_command(command_type, encoded) == command


def test_codec_rejects_future_schema_version() -> None:
    data = b'{"schema_version":99,"run_id":"run_1"}'
    with pytest.raises(ContractVersionError) as caught:
        ContractCodec().decode_command(CommandType.RESUME_RUN, data)
    assert caught.value.code == "unsupported_version"
    assert caught.value.version == 99


def test_event_codec_round_trips_version_one() -> None:
    event = EventEnvelope(
        event_id="evt_1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        type="run.started",
        payload={"goal": "demo"},
    )
    codec = ContractCodec()
    assert codec.decode_event(codec.encode_event(event)) == event


def test_event_codec_rejects_future_and_invalid() -> None:
    with pytest.raises(ContractVersionError) as future:
        ContractCodec().decode_event(b'{"schema_version":99,"event_id":"e"}')
    assert future.value.code == "unsupported_version"
    with pytest.raises(ContractVersionError) as missing:
        ContractCodec().decode_event(b'{"event_id":"e"}')
    assert missing.value.code == "missing_version"
    with pytest.raises(ContractVersionError) as invalid:
        ContractCodec().decode_event(b"{not-json")
    assert invalid.value.code == "invalid_contract"

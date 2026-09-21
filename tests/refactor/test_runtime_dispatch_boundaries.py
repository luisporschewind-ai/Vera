"""Import contracts for the Runtime loop, command, and recovery flows."""

from vera.runtime.command_flow import CommandFlow
from vera.runtime.loop_flow import LoopFlow
from vera.runtime.recovery_flow import RecoveryFlow


def test_runtime_dispatch_flow_facades_are_available() -> None:
    assert CommandFlow is not None
    assert LoopFlow is not None
    assert RecoveryFlow is not None
    assert callable(LoopFlow.drive)
    assert callable(CommandFlow.dispatch)
    assert callable(RecoveryFlow.resume)

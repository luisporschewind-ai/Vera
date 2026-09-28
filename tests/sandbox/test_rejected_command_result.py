import json
from pathlib import Path
from unittest.mock import Mock

from vera.contracts.commands import ResolveApproval, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.bash import BashTool
from vera.tools.registry import ToolRegistry


def test_rejected_command_reaches_model_without_starting_process(tmp_path: Path):
    supervisor = Mock()
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path, supervisor=supervisor))
    adapter = FakeModelAdapter(
        [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="command",
                        name="bash",
                        arguments={
                            "argv": ["/bin/cat", "inside.txt"],
                            "cwd": ".",
                            "timeout_seconds": 5,
                        },
                    ),
                ),
            ),
            ModelTurn(finish_reason="stop", assistant_text="用户拒绝执行。"),
        ]
    )
    runtime = VeraRuntime(adapter, registry, tmp_path / "state")
    events = list(
        runtime.handle(
            StartRun(
                goal="读取",
                workspace_root=tmp_path,
                model_profile="fake",
            )
        )
    )
    required = next(event for event in events if event.type == "approval.required")
    resolved = list(
        runtime.handle(
            ResolveApproval(
                run_id=required.payload["run_id"],
                approval_id=required.payload["approval_id"],
                target_hash=required.payload["target_hash"],
                decision="reject",
            )
        )
    )
    supervisor.run.assert_not_called()
    assert not any(event.type == "process.started" for event in resolved)
    completed = next(event for event in resolved if event.type == "tool.completed")
    assert completed.payload["error_code"] == "approval_rejected"
    message = next(message for message in adapter.requests[-1].messages if message.role == "tool")
    payload = json.loads(message.content)
    assert payload["ok"] is False
    assert payload["error_code"] == "approval_rejected"
    assert payload["data"] == ""
    assert payload["trust_level"] == "untrusted"
    assert "exit_code" not in payload

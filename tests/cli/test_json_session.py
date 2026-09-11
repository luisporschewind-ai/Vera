import json
from io import StringIO
from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_json_session import JsonSessionDriver
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import CloseSession, ExecuteSlashCommand, SubmitPrompt
from vera.session.protocol import encode_action
from vera.tools.registry import ToolRegistry


def make_driver(tmp_path: Path, turns: list[ModelTurn]) -> JsonSessionDriver:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = tmp_path / "state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    runtime = VeraRuntime(FakeModelAdapter(turns), ToolRegistry(), state_dir)
    return JsonSessionDriver(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )


def test_json_session_round_trips_prompt_and_outputs_records(tmp_path: Path) -> None:
    driver = make_driver(tmp_path, [ModelTurn(assistant_text="你好", finish_reason="stop")])
    source = StringIO(
        encode_action(SubmitPrompt(text="你好")) + "\n" + encode_action(CloseSession()) + "\n"
    )
    target = StringIO()
    assert driver.run(source, target) == 0
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    assert records[0]["record_type"] == "event"
    assert any(item.get("event") and item["event"]["type"] == "run.completed" for item in records)
    assert "\u001b" not in target.getvalue()


def test_invalid_line_emits_structured_error_and_continues(tmp_path: Path) -> None:
    driver = make_driver(tmp_path, [])
    source = StringIO("not-json\n" + encode_action(ExecuteSlashCommand(raw="/status")) + "\n")
    target = StringIO()
    assert driver.run(source, target) == 0
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    assert records[0]["event"]["type"] == "session.input_failed"
    assert any(item.get("event") and item["event"]["type"] == "session.status" for item in records)

import errno
import json
from io import StringIO
from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_json_session import JsonSessionDriver
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelTurn, ModelUsage
from vera.runtime.engine import VeraRuntime
from vera.session.actions import (
    CloseSession,
    ExecuteSlashCommand,
    QueuePrompt,
    SubmitPrompt,
)
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


def test_json_session_exposes_normalized_cache_facts_without_provider_payload(
    tmp_path: Path,
) -> None:
    driver = make_driver(
        tmp_path,
        [
            ModelTurn(
                assistant_text="ok",
                finish_reason="stop",
                usage=ModelUsage(
                    input_tokens=100,
                    output_tokens=5,
                    total_tokens=105,
                    cache_hit_input_tokens=60,
                    cache_miss_input_tokens=40,
                ),
            )
        ],
    )
    source = StringIO(
        encode_action(SubmitPrompt(text="hello"))
        + "\n"
        + encode_action(ExecuteSlashCommand(raw="/usage"))
        + "\n"
        + encode_action(ExecuteSlashCommand(raw="/trace"))
        + "\n"
        + encode_action(CloseSession())
        + "\n"
    )
    target = StringIO()
    assert driver.run(source, target) == 0
    events = [
        json.loads(line)["event"]
        for line in target.getvalue().splitlines()
        if json.loads(line).get("event")
    ]
    model = next(event for event in events if event["type"] == "model.completed")
    usage = next(event for event in events if event["type"] == "session.usage")
    trace = next(event for event in events if event["type"] == "session.trace")
    assert model["payload"]["usage"]["cache_hit_input_tokens"] == 60
    assert usage["payload"]["cache_hit_percent"] == 60.0
    assert trace["payload"]["trace"]["run_id"]
    assert trace["payload"]["trace"]["status"] == "completed"
    assert "Run ID" in trace["payload"]["text"]
    assert "hello" not in json.dumps(trace["payload"], ensure_ascii=False)
    assert "FAKE_API_KEY" not in target.getvalue()


def test_invalid_line_emits_structured_error_and_continues(tmp_path: Path) -> None:
    driver = make_driver(tmp_path, [])
    source = StringIO("not-json\n" + encode_action(ExecuteSlashCommand(raw="/status")) + "\n")
    target = StringIO()
    assert driver.run(source, target) == 0
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    assert records[0]["event"]["type"] == "session.input_failed"
    status = next(item["event"] for item in records if item["event"]["type"] == "session.status")
    assert status["payload"]["reasoning"]["mode"] == "unavailable"
    assert status["payload"]["reasoning"]["effort"] is None
    assert "\u001b" not in target.getvalue()


def test_json_session_queues_without_parsing_ui_text(tmp_path: Path) -> None:
    driver = make_driver(tmp_path, [])
    driver.controller.mark_active("run_1")
    source = StringIO(
        encode_action(QueuePrompt(text="later")) + "\n" + encode_action(CloseSession()) + "\n"
    )
    target = StringIO()
    assert driver.run(source, target) == 0
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    queued = next(
        item["event"] for item in records if item["event"]["type"] == "session.prompt_queued"
    )
    assert queued["payload"]["queued"] is True
    assert "later" not in json.dumps(queued["payload"], ensure_ascii=False)
    assert "\u001b" not in target.getvalue()


def test_json_help_and_doctor_are_structured_events(tmp_path: Path) -> None:
    driver = make_driver(tmp_path, [])
    source = StringIO(
        encode_action(ExecuteSlashCommand(raw="/help"))
        + "\n"
        + encode_action(ExecuteSlashCommand(raw="/doctor"))
        + "\n"
        + encode_action(CloseSession())
        + "\n"
    )
    target = StringIO()
    assert driver.run(source, target) == 0
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    types = [item["event"]["type"] for item in records if item.get("event")]
    assert "session.help" in types
    assert "session.doctor" in types
    doctor = next(item["event"] for item in records if item["event"]["type"] == "session.doctor")
    names = [entry["name"] for entry in doctor["payload"]["items"]]
    assert names == ["version", "python", "terminal", "config", "state_dir", "git"]
    assert "\u001b" not in target.getvalue()
    assert "sk-" not in target.getvalue()


def test_json_persistence_warning_is_structured(tmp_path: Path) -> None:
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
    runtime = VeraRuntime(
        FakeModelAdapter([ModelTurn(assistant_text="你好", finish_reason="stop")]),
        ToolRegistry(),
        state_dir,
    )
    from vera.persistence.session_store import ConversationSessionStore
    from vera.session.controller import SessionController

    class FailStore(ConversationSessionStore):
        def append_turn(self, session_id, turn):  # type: ignore[no-untyped-def]
            raise OSError(errno.ENOSPC, "No space left on device")

    deps = RuntimeDependencies(runtime=runtime, config=config, installation_id="json-test")
    controller = SessionController(
        deps,
        workspace,
        "fake",
        session_store=FailStore(state_dir, "json-test"),
    )
    driver = JsonSessionDriver(deps, workspace, "fake", controller=controller)
    source = StringIO(
        encode_action(SubmitPrompt(text="你好")) + "\n" + encode_action(CloseSession()) + "\n"
    )
    target = StringIO()
    assert driver.run(source, target) == 0
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    changed = next(
        item["event"] for item in records if item["event"]["type"] == "session.persistence_changed"
    )
    assert changed["payload"]["state"] == "unsaved"
    assert changed["payload"]["error_code"]
    assert "advice" in changed["payload"]
    assert "session.jsonl" not in target.getvalue()
    assert "\u001b" not in target.getvalue()

from __future__ import annotations

from io import StringIO
from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_driver import drive_run
from vera.cli_exit_codes import SUCCESS, USER_CANCEL, exit_code_for_events
from vera.cli_json_session import JsonSessionDriver
from vera.cli_plain_session import PlainSessionDriver
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.commands import StartRun
from vera.contracts.compatibility import current_compatibility_manifest
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import (
    CloseSession,
    ExecuteSlashCommand,
    QueuePrompt,
    ResolveSessionApproval,
    SubmitPrompt,
)
from vera.session.command_catalog import CommandCatalog
from vera.session.controller import SessionController, SessionSnapshot
from vera.session.protocol import SessionActionCodec, encode_action
from vera.tools.registry import ToolRegistry

GOAL = "把 hello.txt 改为 new"
PHASE6_COMMANDS = {
    "/diff",
    "/review",
    "/doctor",
    "/config",
    "/usage",
    "/shortcuts",
    "/theme",
}
DOCTOR_ITEMS = ("version", "python", "terminal", "config", "state_dir", "git")


class ScriptedIO:
    def __init__(self, inputs: list[str]) -> None:
        self.inputs = inputs
        self.output: list[str] = []

    def read(self, prompt: str) -> str:
        self.output.append(prompt)
        if not self.inputs:
            raise EOFError
        return self.inputs.pop(0)

    def write(self, text: str) -> None:
        self.output.append(text)

    def clear(self) -> None:
        return None


def _proposal() -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id="1",
                name="propose_changeset",
                arguments={
                    "summary": "update hello.txt",
                    "changes": [
                        {
                            "operation": "update",
                            "path": "hello.txt",
                            "after_content": "new\n",
                        }
                    ],
                },
            ),
        ),
    )


def _config(state_dir: Path) -> VeraConfig:
    return VeraConfig(
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


def _workspace(root: Path, name: str) -> Path:
    workspace = root / name
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    return workspace


def _deps(root: Path, name: str) -> tuple[RuntimeDependencies, Path]:
    workspace = _workspace(root, f"{name}-ws")
    state_dir = root / f"{name}-state"
    runtime = VeraRuntime(FakeModelAdapter([_proposal()]), ToolRegistry(), state_dir)
    return RuntimeDependencies(runtime=runtime, config=_config(state_dir)), workspace


def _collect(controller: SessionController, action: object) -> list[EventEnvelope]:
    events: list[EventEnvelope] = []
    for item in controller.dispatch(action):  # type: ignore[arg-type]
        if isinstance(item, EventEnvelope):
            events.append(item)
    return events


def _facts(events: tuple[EventEnvelope, ...] | list[EventEnvelope]) -> dict[str, object]:
    approvals = [event for event in events if event.type == "approval.required"]
    proposed = [event for event in events if event.type == "changeset.proposed"]
    applied = [event for event in events if event.type == "changeset.applied"]
    failed = [event for event in events if event.type in {"run.failed", "model.failed"}]
    rejected = [event for event in events if event.type == "session.action_rejected"]
    terminal_event = next(
        (
            event
            for event in reversed(events)
            if event.type in {"run.completed", "run.failed", "run.cancelled"}
        ),
        None,
    )
    return {
        "terminal": None if terminal_event is None else terminal_event.type,
        "approval_kinds": [event.payload.get("kind") for event in approvals],
        "approval_target_hashes": [event.payload.get("target_hash") for event in approvals],
        "changeset_hashes": [event.payload.get("content_hash") for event in proposed],
        "applied": bool(applied),
        "error_codes": [
            event.payload.get("reason") or event.payload.get("reason_code") for event in failed
        ],
        "rejected_codes": [event.payload.get("reason_code") for event in rejected],
        "exit_code": exit_code_for_events(
            (terminal_event,) if terminal_event is not None else tuple(events)
        ),
    }


def _session_payloads(events: list[EventEnvelope], event_type: str) -> list[dict[str, object]]:
    return [dict(event.payload) for event in events if event.type == event_type]


def _drive_controller(
    root: Path, name: str, *, via_json: bool, decision: str
) -> list[EventEnvelope]:
    deps, _workspace_path = _deps(root, name)
    controller = SessionController(deps, _workspace_path, "fake")
    collected: list[EventEnvelope] = []
    actions: list[object] = [
        ExecuteSlashCommand(raw="/help"),
        ExecuteSlashCommand(raw="/doctor"),
        SubmitPrompt(text=GOAL),
    ]
    for action in actions:
        current = SessionActionCodec.decode(encode_action(action)) if via_json else action
        collected.extend(_collect(controller, current))
        pending = next(
            (event for event in reversed(collected) if event.type == "approval.required"),
            None,
        )
        if pending is not None and action == actions[-1]:
            resolve = ResolveSessionApproval(
                approval_id=str(pending.payload["approval_id"]),
                decision=decision,  # type: ignore[arg-type]
            )
            current_resolve = (
                SessionActionCodec.decode(encode_action(resolve)) if via_json else resolve
            )
            collected.extend(_collect(controller, current_resolve))
    collected.extend(_collect(controller, ExecuteSlashCommand(raw="/diff")))
    return collected


def _drive_plain(
    root: Path, name: str, *, decision: str
) -> tuple[list[EventEnvelope], int, list[str]]:
    deps, workspace = _deps(root, name)
    controller = SessionController(deps, workspace, "fake")
    collected: list[EventEnvelope] = []
    original = controller.dispatch

    def wrapped(action):  # type: ignore[no-untyped-def]
        for item in original(action):
            if isinstance(item, EventEnvelope):
                collected.append(item)
            yield item

    controller.dispatch = wrapped  # type: ignore[method-assign]
    io = ScriptedIO(["/help", "/doctor", GOAL, decision, "/diff", "/exit"])
    code = PlainSessionDriver(deps, workspace, "fake", io, controller=controller).run()
    return collected, code, io.output


def _drive_oneshot(root: Path, name: str, *, decision: str) -> list[EventEnvelope]:
    workspace = _workspace(root, f"{name}-ws")
    runtime = VeraRuntime(FakeModelAdapter([_proposal()]), ToolRegistry(), root / f"{name}-state")
    return list(
        drive_run(
            runtime,
            StartRun(goal=GOAL, workspace_root=workspace, model_profile="fake"),
            lambda _event: decision,
            lambda _batch: None,
        )
    )


def test_phase6_commands_are_discoverable_from_shared_catalog() -> None:
    catalog = CommandCatalog()
    names = {item.name for item in catalog.all()}
    assert names >= PHASE6_COMMANDS
    help_text = catalog.help_text(
        SessionSnapshot(
            session_id="s1",
            active_run_id=None,
            pending_approval_id=None,
            model_profile="fake",
            closed=False,
        )
    )
    assert "开始" in help_text
    assert "/doctor" in help_text
    parsed = catalog.parse(["/docotr"])
    assert parsed.unknown is True
    assert "/doctor" in parsed.suggestions
    assert parsed.handler == ""
    actions = {item.name for item in current_compatibility_manifest().session_actions}
    assert actions >= {
        "prompt.submit",
        "session.command",
        "approval.resolve",
        "session.close",
    }


def test_help_doctor_and_offline_edit_align_across_surfaces(tmp_path: Path) -> None:
    tui = _drive_controller(tmp_path, "tui", via_json=False, decision="approve")
    json_events = _drive_controller(tmp_path, "json", via_json=True, decision="approve")
    plain_events, plain_code, plain_output = _drive_plain(tmp_path, "plain", decision="approve")
    oneshot = _drive_oneshot(tmp_path, "oneshot", decision="approve")

    expected = _facts(tui)
    assert expected["terminal"] == "run.completed"
    assert expected["applied"] is True
    assert expected["exit_code"] == SUCCESS
    assert _facts(json_events) == expected
    assert _facts(plain_events) == expected
    oneshot_facts = _facts(oneshot)
    assert oneshot_facts["terminal"] == expected["terminal"]
    assert oneshot_facts["applied"] is True
    assert oneshot_facts["exit_code"] == SUCCESS
    assert oneshot_facts["approval_kinds"] == expected["approval_kinds"]
    assert oneshot_facts["changeset_hashes"]
    assert oneshot_facts["approval_target_hashes"]

    for events in (tui, json_events, plain_events):
        help_payloads = _session_payloads(events, "session.help")
        doctor_payloads = _session_payloads(events, "session.doctor")
        assert help_payloads
        assert "/doctor" in str(help_payloads[0].get("text", ""))
        assert doctor_payloads
        names = [item["name"] for item in doctor_payloads[0]["items"]]  # type: ignore[index]
        assert tuple(names) == DOCTOR_ITEMS
        dumped = str(doctor_payloads[0])
        assert "sk-" not in dumped
        assert "api_key" not in dumped

    assert any("开始" in line or "/doctor" in line for line in plain_output)
    assert any(item in "\n".join(plain_output) for item in ("version", "python"))
    assert plain_code == 0
    assert (tmp_path / "tui-ws" / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "json-ws" / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "plain-ws" / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "oneshot-ws" / "hello.txt").read_text(encoding="utf-8") == "new\n"


def test_cancel_and_rejected_codes_align_across_surfaces(tmp_path: Path) -> None:
    tui = _drive_controller(tmp_path, "tui-cancel", via_json=False, decision="cancel")
    json_events = _drive_controller(tmp_path, "json-cancel", via_json=True, decision="cancel")
    plain_events, plain_code, _output = _drive_plain(tmp_path, "plain-cancel", decision="cancel")
    oneshot = _drive_oneshot(tmp_path, "oneshot-cancel", decision="cancel")

    expected = _facts(tui)
    assert expected["terminal"] == "run.cancelled"
    assert expected["applied"] is False
    assert expected["exit_code"] == USER_CANCEL
    assert _facts(json_events) == expected
    assert _facts(plain_events) == expected
    oneshot_facts = _facts(oneshot)
    assert oneshot_facts["terminal"] == "run.cancelled"
    assert oneshot_facts["applied"] is False
    assert oneshot_facts["exit_code"] == USER_CANCEL
    assert (tmp_path / "tui-cancel-ws" / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert (tmp_path / "json-cancel-ws" / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert (tmp_path / "plain-cancel-ws" / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert (tmp_path / "oneshot-cancel-ws" / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert plain_code == 0

    deps, workspace = _deps(tmp_path, "reject")
    controller = SessionController(deps, workspace, "fake")
    started = _collect(controller, SubmitPrompt(text=GOAL))
    pending = next(event for event in started if event.type == "approval.required")
    rejected = _collect(
        controller,
        QueuePrompt(text="should-not-queue"),
    )
    assert pending.payload.get("kind") == "changeset"
    assert [event.payload.get("reason_code") for event in rejected] == ["approval_pending"]
    json_driver = JsonSessionDriver(deps, workspace, "fake", controller=controller)
    source = StringIO(encode_action(CloseSession()) + "\n")
    target = StringIO()
    assert json_driver.run(source, target) == 0
    assert "\u001b" not in target.getvalue()

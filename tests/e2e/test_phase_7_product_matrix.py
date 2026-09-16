from __future__ import annotations

import errno
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.cli_driver import drive_run
from vera.cli_exit_codes import SUCCESS
from vera.cli_json_session import JsonSessionDriver
from vera.cli_plain_session import PlainSessionDriver
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.commands import StartRun
from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.contracts.sessions import ConversationTurn
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.errors import JournalCorrupt, StateVersionError
from vera.persistence.session_codec import SessionCodec
from vera.persistence.session_store import ConversationSessionStore
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock, format_block_clock
from vera.redaction import Redactor
from vera.runtime.engine import VeraRuntime
from vera.session.actions import (
    CloseSession,
    ExecuteSlashCommand,
    ResolveSessionApproval,
    SubmitPrompt,
)
from vera.session.controller import SessionController
from vera.session.conversation import ConversationContext
from vera.session.protocol import encode_action
from vera.session.startup import SessionOpenRequest, SessionStartupError, SessionStartupService
from vera.terminal.app import VeraTerminalApp
from vera.terminal.theme import SEMANTIC_TOKENS, THEME_NAMES
from vera.terminal.widgets.approval import ApprovalBlockWidget
from vera.terminal.widgets.composer import select_composer_prompt
from vera.terminal.widgets.user_prompt_anchor import UserPromptAnchor
from vera.tools.registry import ToolRegistry

GOAL = "把 hello.txt 改为 new"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "state" / "sessions"


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


def _proposal(content: str) -> ModelTurn:
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
                            "after_content": content,
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


def _deps(
    root: Path, name: str, turns: list[ModelTurn] | None = None
) -> tuple[RuntimeDependencies, Path]:
    workspace = _workspace(root, f"{name}-ws")
    state_dir = root / f"{name}-state"
    runtime = VeraRuntime(
        FakeModelAdapter(turns or [_proposal("new\n")]),
        ToolRegistry(),
        state_dir,
    )
    return RuntimeDependencies(runtime=runtime, config=_config(state_dir)), workspace


def _collect(controller: SessionController, action: object) -> list[EventEnvelope]:
    return [item for item in controller.dispatch(action) if isinstance(item, EventEnvelope)]  # type: ignore[arg-type]


def _facts(events: list[EventEnvelope] | tuple[EventEnvelope, ...]) -> dict[str, object]:
    approvals = [event for event in events if event.type == "approval.required"]
    applied = [event for event in events if event.type == "changeset.applied"]
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
        "applied": bool(applied),
        "exit_code": (
            0 if terminal_event is not None and terminal_event.type == "run.completed" else 1
        ),
    }


def _approve(controller: SessionController, events: list[EventEnvelope]) -> list[EventEnvelope]:
    pending = next(event for event in events if event.type == "approval.required")
    return _collect(
        controller,
        ResolveSessionApproval(approval_id=str(pending.payload["approval_id"]), decision="approve"),
    )


def test_new_two_turns_continue_and_history_run(tmp_path: Path) -> None:
    turns = [
        ModelTurn(assistant_text="这是说明", finish_reason="stop"),
        _proposal("new\n"),
        _proposal("newer\n"),
    ]
    deps, workspace = _deps(tmp_path, "flow", turns)
    first = SessionController(deps, workspace, "fake")
    explained = _collect(first, SubmitPrompt(text="这个项目做什么"))
    assert any(event.type == "run.completed" for event in explained)
    edited = _collect(first, SubmitPrompt(text=GOAL))
    edited.extend(_approve(first, edited))
    assert _facts(edited)["applied"] is True
    runs = _collect(first, ExecuteSlashCommand(raw="/runs"))
    first_run = next(event.run_id for event in edited if event.type == "run.completed")
    _collect(first, CloseSession())
    session_id = first.snapshot().session_id

    store = ConversationSessionStore(deps.config.state_dir, deps.installation_id)
    loaded = SessionStartupService(store).resolve(
        SessionOpenRequest(mode="continue"),
        workspace,
        interactive_tty=True,
    )
    continued_runtime = VeraRuntime(
        FakeModelAdapter([_proposal("newer\n")]),
        ToolRegistry(),
        deps.config.state_dir,
    )
    second = SessionController(
        RuntimeDependencies(
            runtime=continued_runtime,
            config=deps.config,
            installation_id=deps.installation_id,
        ),
        workspace,
        "fake",
        session_store=store,
        loaded_session=loaded,
        source="continued",
    )
    assert second.snapshot().session_id == session_id
    snapshot = second.conversation.snapshot()
    assert any(message.content == "这个项目做什么" for message in snapshot)
    follow = _collect(second, SubmitPrompt(text="改成 newer"))
    follow.extend(_approve(second, follow))
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "newer\n"
    listed = _collect(second, ExecuteSlashCommand(raw="/runs"))
    dumped = str([event.payload for event in runs + listed])
    assert first_run in dumped or any(
        event.type == "session.runs" or "run_" in str(event.payload) for event in listed + runs
    )


def test_controller_plain_json_oneshot_share_edit_facts(tmp_path: Path) -> None:
    tui_deps, tui_ws = _deps(tmp_path, "tui")
    tui = SessionController(tui_deps, tui_ws, "fake")
    tui_events = _collect(tui, SubmitPrompt(text=GOAL))
    tui_events.extend(_approve(tui, tui_events))

    json_deps, json_ws = _deps(tmp_path, "json")
    json_controller = SessionController(json_deps, json_ws, "fake")
    json_driver = JsonSessionDriver(json_deps, json_ws, "fake", controller=json_controller)
    pending = _collect(json_controller, SubmitPrompt(text=GOAL))
    approval_id = next(
        event.payload["approval_id"] for event in pending if event.type == "approval.required"
    )
    target = StringIO()
    json_code = json_driver.run(
        StringIO(
            encode_action(ResolveSessionApproval(approval_id=str(approval_id), decision="approve"))
            + "\n"
            + encode_action(CloseSession())
            + "\n"
        ),
        target,
    )

    plain_deps, plain_ws = _deps(tmp_path, "plain")
    io = ScriptedIO([GOAL, "approve", "/exit"])
    plain_code = PlainSessionDriver(plain_deps, plain_ws, "fake", io).run()

    oneshot_ws = _workspace(tmp_path, "oneshot-ws")
    oneshot_runtime = VeraRuntime(
        FakeModelAdapter([_proposal("new\n")]),
        ToolRegistry(),
        tmp_path / "oneshot-state",
    )
    oneshot = list(
        drive_run(
            oneshot_runtime,
            StartRun(goal=GOAL, workspace_root=oneshot_ws, model_profile="fake"),
            lambda _event: "approve",
            lambda _batch: None,
        )
    )

    expected = _facts(tui_events)
    assert expected["terminal"] == "run.completed"
    assert expected["applied"] is True
    assert expected["exit_code"] == SUCCESS
    assert json_code == 0
    assert "changeset.applied" in target.getvalue() or "run.completed" in target.getvalue()
    assert "\u001b" not in target.getvalue()
    assert plain_code == 0
    assert (tui_ws / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (json_ws / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (plain_ws / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (oneshot_ws / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert _facts(oneshot)["applied"] is True


def test_session_failure_matrix(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    store = ConversationSessionStore(tmp_path / "state", "install-test", Redactor([]))
    startup = SessionStartupService(store)
    with pytest.raises(SessionStartupError) as missing_continue:
        startup.resolve(SessionOpenRequest(mode="continue"), workspace, interactive_tty=True)
    assert missing_continue.value.code == "no_matching_session"
    created = store.create(workspace)
    store.append_turn(
        created.session_id,
        ConversationTurn(
            user_text="列出文件",
            assistant_text="有 README.md。",
            run_id="run_missing",
            terminal_state="completed",
        ),
    )
    with pytest.raises(SessionStartupError) as missing_id:
        startup.resolve(
            SessionOpenRequest(mode="resume_id", session_id="session_missing"),
            workspace,
            interactive_tty=True,
        )
    assert missing_id.value.code in {"session_not_found", "invalid_session_record"}
    with pytest.raises(SessionStartupError) as mismatch:
        startup.resolve(
            SessionOpenRequest(mode="resume_id", session_id=created.session_id),
            other,
            interactive_tty=True,
        )
    assert mismatch.value.code == "session_workspace_mismatch"
    with pytest.raises(SessionStartupError) as picker:
        startup.resolve(SessionOpenRequest(mode="resume_picker"), workspace, interactive_tty=False)
    assert picker.value.code == "picker_requires_id"
    listed = store.list_for_workspace(workspace)
    assert listed[0].latest_run_state == "unavailable"

    journal = tmp_path / "state" / "sessions" / created.session_id / "session.jsonl"
    before = journal.read_bytes()
    journal.write_bytes(before + b'{"session_format_version":1')
    plan = store.inspect_repair(created.session_id, workspace)
    assert plan.failure_code == "truncated_tail"
    journal.write_bytes(before)

    future_id = "session_future"
    future_dir = tmp_path / "state" / "sessions" / future_id
    future_dir.mkdir()
    future_journal = FIXTURES / "v2-future" / "session.jsonl"
    (future_dir / "session.jsonl").write_bytes(future_journal.read_bytes())
    with pytest.raises((SessionStartupError, StateVersionError, JournalCorrupt)):
        store.load(future_id, workspace)

    mid = store.create(workspace)
    mid_path = tmp_path / "state" / "sessions" / mid.session_id / "session.jsonl"
    mid_path.write_text("not-json\n" + mid_path.read_text(encoding="utf-8"), encoding="utf-8")
    mid_plan = store.inspect_repair(mid.session_id, workspace)
    assert mid_plan.repairable_tail_only is False

    with pytest.raises(ValueError, match="capacity exceeded"):
        ConversationContext.restore(
            10,
            session_id="session-too-big",
            messages=(
                ConversationMessage(role="user", content="x" * 20),
                ConversationMessage(role="assistant", content="y" * 20),
            ),
            compaction_count=0,
        )
    v1_line = (FIXTURES / "v1-valid" / "session.jsonl").read_text(encoding="utf-8").splitlines()[0]
    decoded = SessionCodec().decode_line(
        v1_line, expected_session_id="session_demo", expected_sequence=1
    )
    assert decoded.session_format_version == 1


def test_save_failure_keeps_run_and_marks_unsaved(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    deps = RuntimeDependencies(
        runtime=VeraRuntime(
            FakeModelAdapter([ModelTurn(assistant_text="ok", finish_reason="stop")]),
            ToolRegistry(),
            state_dir,
        ),
        config=_config(state_dir),
        installation_id="install-test",
    )
    inner = ConversationSessionStore(state_dir, "install-test")
    controller = SessionController(deps, workspace, "fake", session_store=inner)

    def boom(session_id: str, turn: ConversationTurn) -> object:
        del session_id, turn
        raise OSError(errno.ENOSPC, "No space left on device")

    controller.session_store.append_turn = boom  # type: ignore[method-assign]
    events = _collect(controller, SubmitPrompt(text="hi"))
    assert any(event.type == "run.completed" for event in events)
    changed = next(event for event in events if event.type == "session.persistence_changed")
    assert changed.payload["state"] == "unsaved"


def _terminal_app(tmp_path: Path) -> VeraTerminalApp:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = tmp_path / "state"
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir)
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=_config(state_dir)),
        workspace,
        "fake",
    )
    return VeraTerminalApp(controller, workspace, "fake", animations=False)


def _user_block(block_id: str, body: str, occurred_at: datetime) -> TimelineBlock:
    return TimelineBlock(
        block_id=block_id,
        run_id="run_1",
        kind=BlockKind.USER,
        title="用户",
        body=body,
        status=BlockStatus.SUCCEEDED,
        expanded=True,
        occurred_at=occurred_at,
    )


def _filler(index: int) -> TimelineBlock:
    return TimelineBlock(
        block_id=f"a{index}",
        run_id="run_1",
        kind=BlockKind.ASSISTANT,
        title="助手",
        body="line\n" * 8,
        status=BlockStatus.SUCCEEDED,
        expanded=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(60, 16), (80, 24), (120, 40)])
async def test_visual_matrix_sizes_and_cjk(tmp_path: Path, size: tuple[int, int]) -> None:
    app = _terminal_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        composer = app.query_one("#composer")
        composer.load_text("你好 Vera café 👩‍💻")
        await pilot.pause()
        assert "你好" in composer.text
        assert app.query_one("#terminal-too-small").display is False
        status = str(app.query_one("#status-line").render())
        assert "会话上下文" in status or size[0] < 80
        glyph = select_composer_prompt(unicode=True)
        assert str(app.query_one("#composer-prompt").render()) == glyph
        assert glyph not in composer.text
        if size == (80, 24):
            await pilot.resize_terminal(60, 16)
            await pilot.pause()
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert "你好" in composer.text


@pytest.mark.asyncio
@pytest.mark.parametrize("theme", THEME_NAMES)
async def test_visual_matrix_themes(tmp_path: Path, theme: str) -> None:
    app = _terminal_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        app._apply_theme(theme)
        await pilot.pause()
        assert app.theme == theme
        assert SEMANTIC_TOKENS[theme]["accent"]


@pytest.mark.asyncio
async def test_visual_anchor_clock_and_approval_density(tmp_path: Path) -> None:
    app = _terminal_app(tmp_path)
    stamp = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(block=_user_block("u1", "第一问", stamp)),
                *(AppendBlock(block=_filler(index)) for index in range(40)),
            )
        )
        timeline.scroll_end(animate=False)
        for _ in range(8):
            timeline.refresh_user_sticky()
            await pilot.pause()
            sticky = app.query_one("#user-sticky", UserPromptAnchor)
            if sticky.display:
                break
        sticky = app.query_one("#user-sticky", UserPromptAnchor)
        assert sticky.display is True
        assert sticky.clock_text == format_block_clock(stamp)
        assert "AM" not in sticky.clock_text
        body = "动作 changeset\n目标 notes.md\n风险 low\n效果 写入文件"
        timeline.apply(
            (
                AppendBlock(
                    block=TimelineBlock(
                        block_id="approval_1",
                        run_id="run_1",
                        kind=BlockKind.APPROVAL,
                        title="Approval required · changeset · low",
                        body=body,
                        status=BlockStatus.PENDING,
                        expanded=True,
                        ref_id="approval_1",
                    )
                ),
            )
        )
        await pilot.pause()
        widget = app.query_one("#block-approval_1", ApprovalBlockWidget)
        assert "风险 low" in str(widget._body.render())
        assert widget.styles.margin.top == 0
        assert widget.styles.margin.bottom == 0
        assert widget._cancel.display is True

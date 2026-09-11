from pathlib import Path
from subprocess import CompletedProcess

from vera.bootstrap import RuntimeDependencies
from vera.cli_session import InteractiveSession
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.conversation import ConversationContext
from vera.session.status import SessionStatusService
from vera.tools.registry import ToolRegistry


class ScriptedIO:
    def __init__(self, inputs: list[str | BaseException]) -> None:
        self.inputs = inputs
        self.output: list[str] = []
        self.cleared = 0

    def read(self, prompt: str) -> str:
        self.output.append(prompt)
        value = self.inputs.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def write(self, text: str) -> None:
        self.output.append(text)

    def clear(self) -> None:
        self.cleared += 1


class FakeGitRunner:
    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CompletedProcess[str]:
        del cwd, timeout
        if "symbolic-ref" in argv:
            return CompletedProcess(list(argv), 0, "main\n", "")
        return CompletedProcess(list(argv), 0, "", "")


def dependencies(workspace: Path, turns: list[ModelTurn]) -> RuntimeDependencies:
    state_dir = workspace.parent / "state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(max_conversation_bytes=200_000),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    adapter = FakeModelAdapter(turns)
    runtime = VeraRuntime(adapter, ToolRegistry(), state_dir)
    return RuntimeDependencies(runtime=runtime, config=config)


def make_session(
    workspace: Path,
    turns: list[ModelTurn],
    inputs: list[str | BaseException],
    *,
    conversation: ConversationContext | None = None,
) -> tuple[InteractiveSession, FakeModelAdapter, ScriptedIO]:
    deps = dependencies(workspace, turns)
    io = ScriptedIO(inputs)
    session = InteractiveSession(
        deps,
        workspace,
        "fake",
        io,
        conversation=conversation,
        status_service=SessionStatusService(
            version_reader=lambda: "0.1.0",
            git_runner=FakeGitRunner(),
        ),
    )
    adapter = deps.runtime.adapter
    assert isinstance(adapter, FakeModelAdapter)
    return session, adapter, io


def proposal(call_id: str, content: str) -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id=call_id,
                name="propose_changeset",
                arguments={
                    "summary": "edit",
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


def test_session_runs_two_independent_goals_and_handles_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    session, _adapter, io = make_session(
        workspace,
        [proposal("proposal-1", "first\n"), proposal("proposal-2", "second\n")],
        ["", "first task", "approve", "second task", "reject", "/runs", "/wat", "/exit"],
    )

    result = session.run()

    output = "\n".join(io.output)
    started_goals = [context.command.goal for context in session.dependencies.runtime.runs.values()]
    assert started_goals == ["first task", "second task"]
    assert output.count("Vera > ") >= 3
    assert "未知命令" in output
    assert "first task" in output
    assert result == 0
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "first\n"


def test_session_eof_exits_cleanly(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, _adapter, _io = make_session(workspace, [], [EOFError()])

    assert session.run() == 0


def test_plain_goal_completes_and_returns_to_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, _adapter, io = make_session(
        workspace,
        [ModelTurn(assistant_text="你好，我是 Vera。", finish_reason="stop")],
        ["Hello", "/exit"],
    )

    assert session.run() == 0
    output = "\n".join(io.output)
    assert "任务完成" in output
    assert "任务失败" not in output
    assert "Vera：你好，我是 Vera。" in output
    assert output.count("Vera > ") == 2


def test_empty_goal_response_fails_and_returns_to_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, _adapter, io = make_session(
        workspace,
        [ModelTurn(assistant_text="", finish_reason="stop")],
        ["fail task", "/exit"],
    )

    assert session.run() == 0
    output = "\n".join(io.output)
    assert "任务失败" in output
    assert "empty_model_response" in output
    assert output.count("Vera > ") == 2


def test_show_and_rollback_commands_do_not_call_model(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, adapter, io = make_session(
        workspace, [], ["/show missing", "/rollback missing", "/exit"]
    )

    assert session.run() == 0
    assert not adapter.requests
    output = "\n".join(io.output)
    assert "未找到 run：missing" in output
    assert "未找到可回滚的 Checkpoint：missing" in output


def test_keyboard_interrupt_at_prompt_preserves_session(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, _adapter, io = make_session(workspace, [], [KeyboardInterrupt(), "/exit"])

    assert session.run() == 0
    assert "当前输入已清空" in "\n".join(io.output)
    assert io.output.count("Vera > ") == 2


def test_keyboard_interrupt_at_approval_cancels_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    session, _adapter, io = make_session(
        workspace, [proposal("proposal-1", "new\n")], ["edit", KeyboardInterrupt(), "/exit"]
    )

    assert session.run() == 0
    assert target.read_text(encoding="utf-8") == "old\n"
    assert "任务已取消" in "\n".join(io.output)


def test_second_goal_receives_first_conversation_pair(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, adapter, _io = make_session(
        workspace,
        [
            ModelTurn(assistant_text="你好", finish_reason="stop"),
            ModelTurn(assistant_text="我刚才说你好", finish_reason="stop"),
        ],
        ["Hello", "刚才说了什么？", "/exit"],
    )

    assert session.run() == 0

    second_messages = adapter.requests[1].messages
    assert [(message.role, message.content) for message in second_messages[-3:]] == [
        ("user", "Hello"),
        ("assistant", "你好"),
        ("user", "刚才说了什么？"),
    ]


def test_new_clears_context_and_changes_session_id(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ids = iter(["session-a", "session-b"])
    conversation = ConversationContext(200_000, session_id_factory=lambda: next(ids))
    session, adapter, io = make_session(
        workspace,
        [
            ModelTurn(assistant_text="你好", finish_reason="stop"),
            ModelTurn(assistant_text="新会话", finish_reason="stop"),
        ],
        ["Hello", "/new", "Hi", "/exit"],
        conversation=conversation,
    )

    assert session.run() == 0
    assert session.conversation.stats().session_id == "session-b"
    assert all(message.content != "Hello" for message in adapter.requests[1].messages)
    assert "已开始新会话：session-b" in "\n".join(io.output)


def test_clear_resets_context_and_clears_display(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, _adapter, io = make_session(
        workspace,
        [ModelTurn(assistant_text="你好", finish_reason="stop")],
        ["Hello", "/clear", "/exit"],
    )

    assert session.run() == 0
    assert io.cleared == 1
    assert session.conversation.snapshot() == ()
    assert "已清空显示并开始新会话" in "\n".join(io.output)


def test_readonly_commands_do_not_call_model(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, adapter, io = make_session(
        workspace,
        [],
        ["/status", "/context", "/permissions", "/help", "/exit"],
    )

    assert session.run() == 0
    assert not adapter.requests
    output = "\n".join(io.output)
    assert "Model       fake / fake-model" in output
    assert "Context" in output
    assert "no OS sandbox" in output
    assert "/compact" in output
    assert "/model" in output


def test_startup_shows_status_before_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session, _adapter, io = make_session(workspace, [], ["/exit"])

    assert session.run() == 0
    assert io.output[0].startswith("Vera 0.1.0")
    assert "输入 /help 查看命令" in io.output
    assert "Vera > " in io.output


def test_context_limit_blocks_natural_language_but_allows_new(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    conversation = ConversationContext(20, session_id_factory=lambda: "session-1")
    conversation.record_response("hello", "hi there!!")
    session, adapter, io = make_session(
        workspace,
        [ModelTurn(assistant_text="recovered", finish_reason="stop")],
        ["more text here", "/new", "ok", "/exit"],
        conversation=conversation,
    )

    assert session.run() == 0
    output = "\n".join(io.output)
    assert "当前上下文已满" in output
    assert len(adapter.requests) == 1
    assert adapter.requests[0].messages[-1].content == "ok"


def test_warning_prompts_compact_after_near_capacity_response(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    conversation = ConversationContext(100, session_id_factory=lambda: "session-1")
    session, _adapter, io = make_session(
        workspace,
        [ModelTurn(assistant_text="b" * 40, finish_reason="stop")],
        ["a" * 40, "/exit"],
        conversation=conversation,
    )

    assert session.run() == 0
    assert "上下文已接近上限" in "\n".join(io.output)
    assert "/compact" in "\n".join(io.output)

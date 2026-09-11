from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.cli_session import InteractiveSession
from vera.config import Limits, VeraConfig
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


class ScriptedIO:
    def __init__(self, inputs: list[str | BaseException]) -> None:
        self.inputs = inputs
        self.output: list[str] = []

    def read(self, prompt: str) -> str:
        self.output.append(prompt)
        value = self.inputs.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def write(self, text: str) -> None:
        self.output.append(text)


def dependencies(workspace: Path, turns: list[ModelTurn]) -> RuntimeDependencies:
    state_dir = workspace.parent / "state"
    config = VeraConfig(state_dir=state_dir, limits=Limits(), providers={})
    runtime = VeraRuntime(FakeModelAdapter(turns), ToolRegistry(), state_dir)
    return RuntimeDependencies(runtime=runtime, config=config)


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
    deps = dependencies(
        workspace,
        [proposal("proposal-1", "first\n"), proposal("proposal-2", "second\n")],
    )
    io = ScriptedIO(
        ["", "first task", "approve", "second task", "reject", "/runs", "/wat", "/exit"]
    )

    result = InteractiveSession(deps, workspace, "fake", io).run()

    output = "\n".join(io.output)
    started_goals = [context.command.goal for context in deps.runtime.runs.values()]
    assert started_goals == ["first task", "second task"]
    assert output.count("Vera > ") >= 3
    assert "未知命令" in output
    assert "first task" in output
    assert result == 0
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "first\n"


def test_session_eof_exits_cleanly(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    io = ScriptedIO([EOFError()])

    assert InteractiveSession(dependencies(workspace, []), workspace, "fake", io).run() == 0


def test_plain_goal_completes_and_returns_to_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    io = ScriptedIO(["Hello", "/exit"])
    turn = ModelTurn(assistant_text="你好，我是 Vera。", finish_reason="stop")

    assert InteractiveSession(dependencies(workspace, [turn]), workspace, "fake", io).run() == 0
    output = "\n".join(io.output)
    assert "任务完成" in output
    assert "任务失败" not in output
    assert "assistant.message" in output
    assert output.count("Vera > ") == 2


def test_empty_goal_response_fails_and_returns_to_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    io = ScriptedIO(["fail task", "/exit"])
    turn = ModelTurn(assistant_text="", finish_reason="stop")

    assert InteractiveSession(dependencies(workspace, [turn]), workspace, "fake", io).run() == 0
    output = "\n".join(io.output)
    assert "任务失败" in output
    assert "empty_model_response" in output
    assert output.count("Vera > ") == 2


def test_show_and_rollback_commands_do_not_call_model(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deps = dependencies(workspace, [])
    io = ScriptedIO(["/show missing", "/rollback missing", "/exit"])

    assert InteractiveSession(deps, workspace, "fake", io).run() == 0
    assert not deps.runtime.adapter.requests
    output = "\n".join(io.output)
    assert "未找到 run：missing" in output
    assert "未找到可回滚的 Checkpoint：missing" in output


def test_keyboard_interrupt_at_prompt_preserves_session(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    io = ScriptedIO([KeyboardInterrupt(), "/exit"])

    assert InteractiveSession(dependencies(workspace, []), workspace, "fake", io).run() == 0
    assert "当前输入已清空" in "\n".join(io.output)
    assert io.output.count("Vera > ") == 2


def test_keyboard_interrupt_at_approval_cancels_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    deps = dependencies(workspace, [proposal("proposal-1", "new\n")])
    io = ScriptedIO(["edit", KeyboardInterrupt(), "/exit"])

    assert InteractiveSession(deps, workspace, "fake", io).run() == 0
    assert target.read_text(encoding="utf-8") == "old\n"
    assert "任务已取消" in "\n".join(io.output)

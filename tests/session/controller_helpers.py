import errno
from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.sessions import ConversationTurn
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.session_store import ConversationSessionStore
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.tools.registry import ToolRegistry


def make_controller(
    workspace: Path,
    turns: list[ModelTurn],
    *,
    editor_argv: tuple[str, ...] = (),
    adapter: FakeModelAdapter | None = None,
) -> SessionController:
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
        editor_argv=editor_argv,
    )
    runtime = VeraRuntime(adapter or FakeModelAdapter(turns), ToolRegistry(), state_dir)
    deps = RuntimeDependencies(runtime=runtime, config=config)
    return SessionController(deps, workspace, "fake")


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


class RecordingSessionStore:
    def __init__(self, inner: ConversationSessionStore) -> None:
        self.inner = inner
        self.calls: list[str] = []
        self.fail_on: str | None = None

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)

    def create(self, workspace: Path):  # type: ignore[no-untyped-def]
        self.calls.append("create")
        if self.fail_on == "create":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.create(workspace)

    def append_turn(self, session_id: str, turn: ConversationTurn):  # type: ignore[no-untyped-def]
        self.calls.append("append_turn")
        if self.fail_on == "append_turn":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.append_turn(session_id, turn)

    def append_compaction(self, session_id: str, summary: str, through_sequence: int):  # type: ignore[no-untyped-def]
        self.calls.append("append_compaction")
        if self.fail_on == "append_compaction":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.append_compaction(session_id, summary, through_sequence)

    def close(self, session_id: str, reason: str):  # type: ignore[no-untyped-def]
        self.calls.append("close")
        if self.fail_on == "close":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.close(session_id, reason)


def make_persistent_controller(
    workspace: Path,
    turns: list[ModelTurn],
    *,
    store: RecordingSessionStore | None = None,
    loaded_session=None,
    source=None,
) -> tuple[SessionController, RecordingSessionStore]:
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
    runtime = VeraRuntime(FakeModelAdapter(turns), ToolRegistry(), state_dir)
    deps = RuntimeDependencies(runtime=runtime, config=config, installation_id="install-test")
    inner = ConversationSessionStore(state_dir, "install-test")
    wrapped = store or RecordingSessionStore(inner)
    controller = SessionController(
        deps,
        workspace,
        "fake",
        session_store=wrapped,
        loaded_session=loaded_session,
        source=source,
    )
    return controller, wrapped

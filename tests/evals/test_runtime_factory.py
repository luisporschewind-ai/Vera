from dataclasses import replace

import pytest

from vera.evals.runtime_factory import EvalRuntimeFactory
from vera.evals.script_driver import EvalExecutionError
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn


def forbidden_call(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("provider loader must not be called")


def test_factory_uses_fake_adapter_and_never_provider_loader(
    loaded_and_isolated, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded, isolated = loaded_and_isolated
    monkeypatch.setattr("vera.bootstrap.read_provider_environment", forbidden_call)
    monkeypatch.setattr("vera.bootstrap.build_runtime", forbidden_call)
    runtime = EvalRuntimeFactory().create(loaded, isolated)
    assert isinstance(runtime.adapter, FakeModelAdapter)


def test_driver_rejects_unknown_tool_and_env_placeholders(loaded_and_isolated) -> None:
    loaded, isolated = loaded_and_isolated
    unknown = loaded.script.model_copy(
        update={
            "turns": (
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(call_id="1", name="WriteFile", arguments={"path": "x"}),
                    ),
                ),
            )
        }
    )
    with pytest.raises(EvalExecutionError, match="unknown_tool"):
        EvalRuntimeFactory().create(replace(loaded, script=unknown), isolated)

    env = loaded.script.model_copy(
        update={
            "turns": (
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="1",
                            name="propose_changeset",
                            arguments={
                                "summary": "edit",
                                "changes": [
                                    {
                                        "operation": "create",
                                        "path": "hello.txt",
                                        "after_content": "hi\n",
                                    }
                                ],
                                "verification": [{"argv": ["$HOME"], "cwd": "."}],
                            },
                        ),
                    ),
                ),
            )
        }
    )
    with pytest.raises(EvalExecutionError, match="illegal_env_placeholder"):
        EvalRuntimeFactory().create(replace(loaded, script=env), isolated)

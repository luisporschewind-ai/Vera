from dataclasses import replace

import pytest

from vera.evals.runtime_factory import EvalRuntimeFactory
from vera.evals.script_driver import EvalExecutionError, ScriptedRunDriver
from vera.models.base import ModelToolCall, ModelTurn


def test_driver_runs_plain_answer_through_core(loaded_and_isolated) -> None:
    loaded, isolated = loaded_and_isolated
    runtime = EvalRuntimeFactory().create(loaded, isolated)
    execution = ScriptedRunDriver().execute(runtime, loaded, isolated)
    assert execution.runtime_instance_count == 1
    assert execution.restart_event_offset is None
    assert execution.event_types[-1] == "run.completed"
    assert execution.before_files == execution.after_files


def test_driver_fails_closed_when_approval_script_is_exhausted(loaded_and_isolated) -> None:
    loaded, isolated = loaded_and_isolated
    script = loaded.script.model_copy(
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
                            },
                        ),
                    ),
                ),
            ),
            "approvals": (),
        }
    )
    loaded = replace(loaded, script=script)
    runtime = EvalRuntimeFactory().create(loaded, isolated)
    with pytest.raises(EvalExecutionError, match="approval_script_exhausted"):
        ScriptedRunDriver().execute(runtime, loaded, isolated)


def test_driver_replaces_eval_python_and_applies_create(loaded_and_isolated) -> None:
    loaded, isolated = loaded_and_isolated
    script = loaded.script.model_copy(
        update={
            "turns": (
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="1",
                            name="propose_changeset",
                            arguments={
                                "summary": "create",
                                "changes": [
                                    {
                                        "operation": "create",
                                        "path": "ok.txt",
                                        "after_content": "ok\n",
                                    }
                                ],
                                "verification": [
                                    {
                                        "argv": ["ruff", "check", "."],
                                        "cwd": ".",
                                    }
                                ],
                            },
                        ),
                    ),
                ),
            ),
            "approvals": ("approve",),
        }
    )
    loaded = replace(loaded, script=script)
    runtime = EvalRuntimeFactory().create(loaded, isolated)
    execution = ScriptedRunDriver().execute(runtime, loaded, isolated)
    assert (isolated.workspace / "ok.txt").read_text(encoding="utf-8") == "ok\n"
    assert execution.side_effect_counts is not None
    assert execution.side_effect_counts["changeset.applied"] == 1
    assert execution.event_types[-1] == "run.completed"

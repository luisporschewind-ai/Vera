"""Assemble an offline VeraRuntime that never loads provider credentials."""

from __future__ import annotations

import sys
from typing import Any

from vera.evals.contracts import EvalScenario
from vera.evals.corpus import LoadedEvalCase
from vera.evals.failpoints import (
    EvalFailpoint,
    EvalFailpointFileWriter,
    EvalFailpointSnapshotStore,
)
from vera.evals.isolation import IsolatedEvalCase
from vera.evals.script_driver import EvalExecutionError
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.policy.engine import PolicyEngine
from vera.policy.snapshot import EffectivePolicySnapshot
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.probe import workspace_identity
from vera.runtime.engine import VeraRuntime
from vera.tools.builtin import ListDirectoryTool, ReadFileTool, SearchTextTool
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths

_ALLOWED_TOOLS = frozenset({"propose_changeset", "read_file", "list_directory", "search_text"})
_EVAL_PYTHON = "$VERA_EVAL_PYTHON"


class EvalRuntimeFactory:
    def __init__(self) -> None:
        self._triggers: dict[EvalFailpoint, int] = {}

    def trigger_count(self, point: EvalFailpoint) -> int:
        return self._triggers.get(point, 0)

    def _mark_trigger(self, point: EvalFailpoint) -> None:
        self._triggers[point] = self._triggers.get(point, 0) + 1

    def create(
        self,
        loaded: LoadedEvalCase,
        isolated: IsolatedEvalCase,
        failpoint: EvalFailpoint | None = None,
        *,
        consume_script: bool = True,
    ) -> VeraRuntime:
        if loaded.case.model != "fake":
            raise EvalExecutionError("unsupported_model", "evaluation model must be fake")
        if failpoint is not None and loaded.case.scenario is EvalScenario.STANDARD:
            raise EvalExecutionError(
                "failpoint_not_allowed",
                "standard evaluation cases cannot enable failpoints",
            )
        turns = tuple(_rewrite_turn(turn) for turn in loaded.script.turns) if consume_script else ()
        adapter = FakeModelAdapter(turns, text_deltas=loaded.script.text_deltas)
        paths = WorkspacePaths(isolated.workspace)
        registry = ToolRegistry()
        registry.register(ReadFileTool(paths, 1_000_000))
        registry.register(ListDirectoryTool(paths))
        registry.register(SearchTextTool(paths))
        installation_id = f"eval-{loaded.case.case_id}"
        identity = workspace_identity(isolated.workspace, installation_id)
        prefixes = (("ruff",),)
        engine = PolicyEngine(
            EffectivePolicySnapshot(
                workspace_identity=identity,
                user_allowed_command_prefixes=prefixes,
            )
        )
        policy = CommandPolicy(
            prefixes,
            policy_engine=engine,
            workspace_identity=identity,
        )
        snapshot_store: RecoverySnapshotStore
        file_writer = None
        if failpoint is EvalFailpoint.AFTER_FIRST_WRITE:
            snapshot_store = RecoverySnapshotStore(isolated.state_dir)
            file_writer = EvalFailpointFileWriter(self._mark_trigger)
        elif failpoint is not None:
            snapshot_store = EvalFailpointSnapshotStore(
                isolated.state_dir, failpoint, self._mark_trigger
            )
        else:
            snapshot_store = RecoverySnapshotStore(isolated.state_dir)
        coordinator = RecoveryCoordinator(
            isolated.state_dir,
            installation_id,
            snapshot_store=snapshot_store,
        )
        return VeraRuntime(
            adapter,
            registry,
            isolated.state_dir,
            command_policy=policy,
            snapshot_store=snapshot_store,
            installation_id=installation_id,
            recovery_coordinator=coordinator,
            policy_engine=engine,
            file_writer=file_writer,
            artifact_prefix=isolated.state_dir.parent / "vera-verification",
        )


def _rewrite_turn(turn: ModelTurn) -> ModelTurn:
    if not turn.tool_calls:
        return turn
    rewritten = tuple(_rewrite_call(call) for call in turn.tool_calls)
    return turn.model_copy(update={"tool_calls": rewritten})


def _rewrite_call(call: ModelToolCall) -> ModelToolCall:
    if call.name not in _ALLOWED_TOOLS:
        raise EvalExecutionError("unknown_tool", f"unsupported evaluation tool {call.name}")
    return call.model_copy(update={"arguments": _rewrite_value(call.arguments)})


def _rewrite_value(value: Any) -> Any:
    if isinstance(value, str):
        if value == _EVAL_PYTHON:
            return sys.executable
        if value.startswith("$") and value != _EVAL_PYTHON:
            raise EvalExecutionError(
                "illegal_env_placeholder",
                "only $VERA_EVAL_PYTHON may appear in evaluation scripts",
            )
        return value
    if isinstance(value, list):
        return [_rewrite_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_value(item) for key, item in value.items()}
    return value

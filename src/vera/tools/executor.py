"""The single Policy-bound execution path for ordinary Core tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from vera.contracts.tool_actions import ToolAction, ToolRiskFacts, tool_action_input_hash
from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyDecision, PolicyDecisionKind
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.registry import ToolRegistry
from vera.workspace.mutation import FileMutationPlanningError, PlannedFileMutation
from vera.workspace.paths import WorkspaceBoundaryError


class ToolPreparationError(ValueError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True)
class PreparedToolAction:
    action: ToolAction
    definition: ToolDefinitionV2
    parsed_arguments: BaseModel
    policy_decision: PolicyDecision
    target_facts_hash: str
    mutation: PlannedFileMutation | None = None


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        policy_engine: PolicyEngine,
        permissions: WorkspacePermissionSnapshot,
        *,
        goal_authorized: bool = False,
        state_dir: Path | None = None,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine
        self.permissions = permissions
        self.goal_authorized = goal_authorized
        self.state_dir = state_dir

    def prepare(self, *, run_id: str, name: str, arguments: dict[str, Any]) -> PreparedToolAction:
        tool = self.registry.implementation(name)
        if tool is None:
            raise ToolPreparationError("unknown_tool")
        try:
            parsed = tool.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolPreparationError("invalid_tool_arguments") from exc
        definition = next(
            (item for item in self.registry.definitions() if item.name == name),
            None,
        )
        if definition is None:
            raise ToolPreparationError("unknown_tool")
        action_id = uuid4().hex
        mutation = self._plan_mutation(tool, run_id, parsed, action_id=action_id)
        facts = self._risk_facts(tool, parsed)
        if mutation is not None:
            facts = facts.model_copy(update={"target_facts_hash": mutation.plan.target_facts_hash})
        normalized = parsed.model_dump(mode="json")
        action = ToolAction(
            action_id=action_id,
            run_id=run_id,
            tool_name=definition.name,
            tool_version=definition.tool_version,
            effects=definition.effects,
            workspace_identity=self.permissions.workspace_identity,
            normalized_arguments=normalized,
            risk_facts=facts,
            input_hash=tool_action_input_hash(
                tool_name=definition.name,
                tool_version=definition.tool_version,
                workspace_identity=self.permissions.workspace_identity,
                effects=definition.effects,
                normalized_arguments=normalized,
                risk_facts=facts,
            ),
        )
        return PreparedToolAction(
            action=action,
            definition=definition,
            parsed_arguments=parsed,
            policy_decision=self.policy_engine.decide_tool_action(
                action, self.permissions, goal_authorized=self.goal_authorized
            ),
            target_facts_hash=_facts_hash(facts),
            mutation=mutation,
        )

    def execute_allowed(
        self, prepared: PreparedToolAction, *, approved: bool = False
    ) -> ToolResult:
        decision = prepared.policy_decision.decision
        if decision is PolicyDecisionKind.DENY:
            return ToolResult(ok=False, error_code="policy_denied")
        if not approved and decision is PolicyDecisionKind.APPROVAL_REQUIRED:
            return ToolResult(
                ok=False,
                error_code="approval_required",
            )
        tool = self.registry.implementation(prepared.definition.name)
        if tool is None:
            return ToolResult(ok=False, error_code="unknown_tool")
        current_definition = next(
            (item for item in self.registry.definitions() if item.name == prepared.definition.name),
            None,
        )
        if current_definition != prepared.definition:
            return ToolResult(ok=False, error_code="stale_tool_action")
        if (
            prepared.action.tool_version != current_definition.tool_version
            or prepared.action.effects != current_definition.effects
            or prepared.action.workspace_identity != self.permissions.workspace_identity
            or prepared.policy_decision.policy_hash != self.policy_engine.policy_hash
        ):
            return ToolResult(ok=False, error_code="stale_tool_action")
        try:
            parsed = tool.input_model.model_validate(dict(prepared.action.normalized_arguments))
        except ValidationError:
            return ToolResult(ok=False, error_code="stale_tool_action")
        mutation = self._plan_mutation(
            tool, prepared.action.run_id, parsed, action_id=prepared.action.action_id
        )
        facts = self._risk_facts(tool, parsed)
        if mutation is not None:
            facts = facts.model_copy(update={"target_facts_hash": mutation.plan.target_facts_hash})
        if _facts_hash(facts) != prepared.target_facts_hash:
            return ToolResult(ok=False, error_code="stale_tool_action")
        normalized = parsed.model_dump(mode="json")
        expected_hash = tool_action_input_hash(
            tool_name=current_definition.name,
            tool_version=current_definition.tool_version,
            workspace_identity=self.permissions.workspace_identity,
            effects=current_definition.effects,
            normalized_arguments=normalized,
            risk_facts=facts,
        )
        if expected_hash != prepared.action.input_hash:
            return ToolResult(ok=False, error_code="stale_tool_action")
        if mutation is not None:
            original = prepared.mutation
            if original is None or not _same_mutation(original, mutation):
                return ToolResult(ok=False, error_code="stale_tool_action")
            applier = getattr(tool, "applier", None)
            if applier is None:
                return ToolResult(ok=False, error_code="mutation_executor_unbound")
            applied = applier.apply(mutation)
            if applied.status.value != "applied":
                return ToolResult(ok=False, error_code=applied.error_code or applied.status.value)
            result = ToolResult(
                ok=True,
                content={
                    "action_id": mutation.plan.action_id,
                    "operation": mutation.plan.operation,
                    "path": mutation.plan.path,
                    "before_hash": mutation.plan.before_hash,
                    "after_hash": mutation.plan.after_hash,
                    "unified_diff": mutation.plan.unified_diff,
                    "status": applied.status.value,
                },
            )
        else:
            result = tool.execute(parsed)
        normalized = result if isinstance(result, ToolResult) else ToolResult.model_validate(result)
        if normalized.content is not None:
            rendered = json.dumps(
                normalized.content, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            if len(rendered) > current_definition.max_output_bytes:
                return ToolResult(ok=False, truncated=True, error_code="output_limit_exceeded")
        return normalized

    @staticmethod
    def _risk_facts(tool: Any, arguments: BaseModel) -> ToolRiskFacts:
        collector = getattr(tool, "risk_facts", None)
        if collector is not None:
            facts = collector(arguments)
        elif hasattr(tool, "paths") and hasattr(arguments, "path"):
            raw_path = str(arguments.path)
            try:
                fact = tool.paths.inspect_read(raw_path)
            except WorkspaceBoundaryError as exc:
                facts = ToolRiskFacts(
                    normalized_paths=(raw_path,),
                    outside_workspace=exc.code
                    in {"not_workspace_relative", "path_escapes_workspace"},
                    protected_target=exc.code == "protected_path",
                    facts_complete=True,
                )
            else:
                facts = ToolRiskFacts(normalized_paths=(fact.relative_path,), facts_complete=True)
        else:
            facts = ToolRiskFacts(facts_complete=False)
        if not isinstance(facts, ToolRiskFacts):
            raise ToolPreparationError("invalid_tool_risk_facts")
        return facts

    def _plan_mutation(
        self, tool: Any, run_id: str, arguments: BaseModel, *, action_id: str | None = None
    ) -> PlannedFileMutation | None:
        planner = getattr(tool, "plan_action", None)
        if planner is None:
            return None
        if self.state_dir is not None:
            binder = getattr(tool, "bind_state", None)
            if binder is not None:
                binder(self.state_dir)
        try:
            planned = planner(run_id, arguments, action_id=action_id)
        except FileMutationPlanningError as exc:
            raise ToolPreparationError(exc.code) from exc
        if not isinstance(planned, PlannedFileMutation):
            raise ToolPreparationError("invalid_mutation_plan")
        return planned

    @staticmethod
    def facts_hash(facts: ToolRiskFacts) -> str:
        return _facts_hash(facts)


def _facts_hash(facts: ToolRiskFacts) -> str:
    payload = json.dumps(
        facts.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _same_mutation(left: PlannedFileMutation, right: PlannedFileMutation) -> bool:
    return (
        left.plan.action_id == right.plan.action_id
        and left.plan.run_id == right.plan.run_id
        and left.plan.path == right.plan.path
        and left.plan.operation == right.plan.operation
        and left.plan.before_hash == right.plan.before_hash
        and left.plan.after_hash == right.plan.after_hash
        and left.plan.target_facts_hash == right.plan.target_facts_hash
        and left.plan.content_hash == right.plan.content_hash
        and left.plan.unified_diff == right.plan.unified_diff
    )

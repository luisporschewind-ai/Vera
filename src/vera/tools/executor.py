"""The single Policy-bound execution path for ordinary Core tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from vera.contracts.tool_actions import ToolAction, ToolRiskFacts, tool_action_input_hash
from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyDecision, PolicyDecisionKind
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.registry import ToolRegistry
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


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        policy_engine: PolicyEngine,
        permissions: WorkspacePermissionSnapshot,
        *,
        goal_authorized: bool = False,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine
        self.permissions = permissions
        self.goal_authorized = goal_authorized

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
        facts = self._risk_facts(tool, parsed)
        normalized = parsed.model_dump(mode="json")
        action = ToolAction(
            action_id=uuid4().hex,
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
        )

    def execute_allowed(
        self, prepared: PreparedToolAction, *, approved: bool = False
    ) -> ToolResult:
        if not approved and prepared.policy_decision.decision is not PolicyDecisionKind.ALLOW:
            return ToolResult(
                ok=False,
                error_code=(
                    "approval_required"
                    if prepared.policy_decision.decision is PolicyDecisionKind.APPROVAL_REQUIRED
                    else "policy_denied"
                ),
            )
        tool = self.registry.implementation(prepared.definition.name)
        if tool is None:
            return ToolResult(ok=False, error_code="unknown_tool")
        try:
            parsed = tool.input_model.model_validate(dict(prepared.action.normalized_arguments))
        except ValidationError:
            return ToolResult(ok=False, error_code="stale_tool_action")
        facts = self._risk_facts(tool, parsed)
        if _facts_hash(facts) != prepared.target_facts_hash:
            return ToolResult(ok=False, error_code="stale_tool_action")
        result = tool.execute(parsed)
        normalized = result if isinstance(result, ToolResult) else ToolResult.model_validate(result)
        if normalized.content is not None:
            rendered = json.dumps(
                normalized.content, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            if len(rendered) > prepared.definition.max_output_bytes:
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

    @staticmethod
    def facts_hash(facts: ToolRiskFacts) -> str:
        return _facts_hash(facts)


def _facts_hash(facts: ToolRiskFacts) -> str:
    payload = json.dumps(
        facts.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

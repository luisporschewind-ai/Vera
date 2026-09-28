"""File permission requests are proposals; only ToolExecutor may approve them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from vera.contracts import ContractModel
from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.sandbox.access import AccessDenied, AccessRequest, AccessSession
from vera.sandbox.files import operation_key
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.registry import ToolRegistry


class FileAccessInput(ContractModel):
    path: str
    mode: Literal["read", "read_write"] = "read"
    scope: Literal["once", "session"] = "once"
    reason: str = Field(min_length=1, max_length=1000)
    target_tool: str | None = None
    target_arguments: dict[str, Any] | None = None

    @model_validator(mode="after")
    def exact_once_operation(self) -> FileAccessInput:
        if self.scope == "once" and (not self.target_tool or self.target_arguments is None):
            raise ValueError("once requires an exact target tool and arguments")
        return self


class RequestFileAccessTool:
    name = "request_file_access"
    input_model = FileAccessInput
    definition = ToolDefinitionV2(
        name=name,
        description=(
            "Ask the user to grant read or read/write access to one outside file/directory. "
            "Directory grants include descendants. A once grant binds exact target_tool and "
            "target_arguments. No network or system privileges."
        ),
        input_schema=FileAccessInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.FILE_ACCESS_GRANT,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=10000,
    )

    def __init__(self, session: AccessSession, registry: ToolRegistry | None = None) -> None:
        self.session = session
        self.registry = registry
        self._requests: dict[str, AccessRequest] = {}

    def _request(self, arguments: FileAccessInput) -> AccessRequest:
        key = f"{self.session.generation}:" + arguments.model_dump_json()
        if key not in self._requests:
            operation_id = None
            if arguments.target_tool is not None and arguments.target_arguments is not None:
                target_arguments = arguments.target_arguments
                if self.registry is not None:
                    tool = self.registry.implementation(arguments.target_tool)
                    if tool is None or isinstance(tool, RequestFileAccessTool):
                        raise AccessDenied("invalid_target_tool")
                    target_arguments = tool.input_model.model_validate(target_arguments).model_dump(
                        mode="json"
                    )
                operation_id = operation_key(arguments.target_tool, target_arguments)
            self._requests[key] = self.session.request(
                Path(arguments.path), arguments.mode, arguments.scope, operation_id=operation_id
            )
        return self._requests[key]

    def risk_facts(self, arguments: FileAccessInput) -> ToolRiskFacts:
        try:
            request = self._request(arguments)
            request.identity.validate()
        except AccessDenied as exc:
            return ToolRiskFacts(
                policy_forbidden=True, policy_reason_code=str(exc), facts_complete=True
            )
        binding = {
            "request_id": request.request_id,
            "path": str(request.path),
            "device": request.identity.device,
            "inode": request.identity.inode,
            "recursive": request.recursive,
        }
        return ToolRiskFacts(
            normalized_paths=(str(request.path),),
            external_target=str(request.path),
            facts_complete=True,
            target_facts_hash=hashlib.sha256(
                json.dumps(binding, sort_keys=True).encode()
            ).hexdigest(),
        )

    def approval_description(self, arguments: FileAccessInput) -> str:
        request = self._request(arguments)
        mode = "只读" if request.mode == "read" else "读写"
        scope = "仅本次操作" if request.scope == "once" else "本次会话"
        children = "（包含子目录）" if request.recursive else "（仅此文件）"
        return (
            f"访问 {request.path} {children}；权限：{mode}；有效期：{scope}。"
            f"用途：{arguments.reason}"
        )

    def execute(self, arguments: FileAccessInput) -> ToolResult:
        return ToolResult(ok=False, error_code="approval_required")

    def execute_approved(self, arguments: FileAccessInput) -> ToolResult:
        request = self._request(arguments)
        try:
            grant = self.session.resolve(request.request_id, approved=True)
        except AccessDenied as exc:
            return ToolResult(ok=False, error_code=str(exc))
        self._requests.pop(f"{self.session.generation}:" + arguments.model_dump_json(), None)
        return ToolResult(
            ok=True,
            content={
                "grant_id": grant.grant_id if grant else None,
                "path": str(request.path),
                "mode": request.mode,
                "scope": request.scope,
                "recursive": request.recursive,
            },
        )

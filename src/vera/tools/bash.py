"""Structured, shell-free process execution for Vera's Core tool surface."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vera.contracts.process_actions import BashInput, CommandActionPlan
from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.policy.models import RiskLevel
from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessSupervisor
from vera.sandbox.apple_services import APPLE_IOS_BUILD_SERVICES, requests_approved_ios_build
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths

_SHELLS = frozenset({"sh", "bash", "zsh", "fish", "dash", "cmd", "powershell", "pwsh"})
_PRIVILEGED = frozenset({"sudo", "doas", "su"})
_DESTRUCTIVE = frozenset({"rm", "rmdir", "unlink", "del"})
_NETWORK = frozenset({"curl", "wget", "nc", "ssh", "scp", "ftp", "http", "https"})
_INSTALLERS = frozenset({"pip", "pip3", "uv", "npm", "pnpm", "yarn", "cargo", "brew", "gem"})
_BUILD_COMMANDS = frozenset({"make", "cmake", "xcodebuild", "swift", "go", "gradle", "mvn"})
_GENERATORS = frozenset({"black", "isort", "prettier", "rustfmt", "gofmt", "protoc"})
_WRITE_COMMANDS = frozenset(
    {"mv", "cp", "mkdir", "touch", "chmod", "ln", "sed", "perl"} | _GENERATORS
)
_GIT_WRITE_COMMANDS = frozenset(
    {
        "add",
        "am",
        "apply",
        "branch",
        "checkout",
        "cherry-pick",
        "clean",
        "commit",
        "config",
        "fetch",
        "merge",
        "mv",
        "pull",
        "push",
        "rebase",
        "remote",
        "reset",
        "restore",
        "revert",
        "rm",
        "stash",
        "submodule",
        "switch",
        "tag",
        "update-index",
        "worktree",
    }
)


def executable_name(value: str) -> str:
    return Path(value).name.lower().removesuffix(".exe")


def classify_argv(argv: tuple[str, ...]) -> dict[str, Any]:
    """Return conservative facts for a structured command without executing it."""

    executable = executable_name(argv[0]) if argv else ""
    git_write = executable == "git" and len(argv) > 1 and argv[1] in _GIT_WRITE_COMMANDS
    shell = executable in _SHELLS or any(token in _SHELLS for token in argv[1:])
    privileged = executable in _PRIVILEGED or any(token in _PRIVILEGED for token in argv[1:])
    destructive = executable in _DESTRUCTIVE or (
        executable == "git"
        and len(argv) > 1
        and (
            argv[1] in {"clean", "checkout", "restore"}
            or (argv[1] == "reset" and "--hard" in argv[2:])
        )
    )
    network = (
        executable in _NETWORK
        or any(token.startswith(("http://", "https://")) for token in argv)
        or (
            executable == "git"
            and len(argv) > 1
            and argv[1] in {"clone", "fetch", "pull", "push", "submodule"}
        )
    )
    installer = executable in _INSTALLERS and any(
        token in {"install", "add", "update", "upgrade"} for token in argv[1:]
    )
    build = executable in _BUILD_COMMANDS or (
        executable in {"npm", "pnpm", "yarn", "cargo", "uv"}
        and any(token in {"build", "run", "compile", "test"} for token in argv[1:])
    )
    service = any(token in {"serve", "server", "http.server", "dev-server"} for token in argv[1:])
    writes = executable in _WRITE_COMMANDS or (
        executable == "git"
        and len(argv) > 1
        and argv[1]
        in {
            "add",
            "commit",
            "merge",
            "rebase",
            "cherry-pick",
            "stash",
            "tag",
            "branch",
            "push",
            "pull",
        }
    )
    secret_names = ("api_key", "api-token", "authorization", "private_key", "password", "secret")
    secret = any(
        token.startswith(("--password", "--token", "--api-key", "--secret"))
        or any(token.lower().startswith(f"{name}=") for name in secret_names)
        for token in argv
    )
    forbidden = shell or privileged or destructive or secret or git_write
    if shell or privileged or destructive or secret:
        risk = RiskLevel.FORBIDDEN
    elif network or installer or writes or build or service:
        risk = RiskLevel.HIGH
    elif executable in {
        "rg",
        "grep",
        "find",
        "ls",
        "cat",
        "head",
        "tail",
        "pwd",
        "python",
        "python3",
        "pytest",
        "ruff",
        "mypy",
        "git",
    }:
        risk = RiskLevel.LOW
    else:
        risk = RiskLevel.MODERATE
    return {
        "executable": executable,
        "shell": shell,
        "privileged": privileged,
        "destructive": destructive,
        "network": network,
        "installer": installer,
        "build": build,
        "service": service,
        "writes": writes,
        "git_write": git_write,
        "secret": secret,
        "risk_level": risk,
        "external_target": "network" if network else None,
        "forbidden": forbidden,
        "policy_reason_code": "use_native_git_tool" if git_write else None,
    }


def _forbidden_reason(facts: dict[str, Any]) -> str | None:
    if facts["git_write"]:
        return "use_native_git_tool"
    if facts["shell"]:
        return "shell_forbidden"
    if facts["privileged"]:
        return "privilege_forbidden"
    if facts["destructive"]:
        return "destructive_command_forbidden"
    if facts["secret"]:
        return "secret_access_forbidden"
    return None


def _apple_build_service_facts_hash(argv: tuple[str, ...]) -> str:
    from vera.sandbox.apple_volume import APPLE_BUILD_STORAGE

    payload = {
        "capability": "apple_ios_build_services",
        "services": list(APPLE_IOS_BUILD_SERVICES),
        "build_storage": APPLE_BUILD_STORAGE,
        "xcodebuild": str(Path(argv[0]).resolve()),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class BashTool:
    name = "bash"
    input_model = BashInput
    description = "Run one structured argv process inside the workspace without shell parsing."
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=BashInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.PROCESS_EXECUTE,),
        supports_cancellation=True,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def __init__(
        self,
        workspace: Path,
        supervisor: ProcessSupervisor | None = None,
        *,
        max_output_bytes: int = 100_000,
        environment_source: dict[str, str] | None = None,
    ) -> None:
        self.paths = WorkspacePaths(workspace)
        self.workspace = self.paths.root
        self.supervisor = supervisor or ProcessSupervisor()
        self.max_output_bytes = max_output_bytes
        self.environment_source = environment_source

    def normalized_cwd(self, arguments: BashInput) -> Path:
        try:
            fact = self.paths.inspect_read(arguments.cwd)
        except WorkspaceBoundaryError as exc:
            raise ValueError(exc.code) from exc
        if not fact.exists or fact.kind != "directory":
            raise ValueError("cwd_not_directory")
        return Path(fact.canonical_path)

    def effects(self, arguments: BashInput) -> tuple[ToolEffect, ...]:
        facts = classify_argv(arguments.argv)
        effects: list[ToolEffect] = [ToolEffect.PROCESS_EXECUTE]
        if facts["writes"]:
            effects.append(ToolEffect.WORKSPACE_WRITE)
        if facts["network"]:
            effects.append(ToolEffect.NETWORK_ACCESS)
        if requests_approved_ios_build(arguments.argv):
            effects.append(ToolEffect.APPLE_IOS_BUILD_SERVICES)
        return tuple(effects)

    def risk_facts(self, arguments: BashInput) -> ToolRiskFacts:
        facts = classify_argv(arguments.argv)
        service_facts_hash = (
            _apple_build_service_facts_hash(arguments.argv)
            if requests_approved_ios_build(arguments.argv)
            else None
        )
        try:
            cwd = self.normalized_cwd(arguments)
        except ValueError as exc:
            return ToolRiskFacts(
                argv=arguments.argv,
                cwd=arguments.cwd,
                normalized_paths=(arguments.cwd,),
                outside_workspace=str(exc) in {"not_workspace_relative", "path_escapes_workspace"},
                destructive=bool(facts["destructive"]),
                external_target=facts["external_target"],
                secrets_present=bool(facts["secret"]),
                policy_forbidden=bool(facts["forbidden"]),
                policy_reason_code=_forbidden_reason(facts),
                facts_complete=True,
            )
        return ToolRiskFacts(
            argv=arguments.argv,
            cwd=str(cwd.relative_to(self.workspace).as_posix() or "."),
            normalized_paths=(str(cwd.relative_to(self.workspace).as_posix() or "."),),
            destructive=bool(facts["destructive"]),
            external_target=facts["external_target"],
            secrets_present=bool(facts["secret"]),
            policy_forbidden=bool(facts["forbidden"]),
            policy_reason_code=_forbidden_reason(facts),
            facts_complete=True,
            target_facts_hash=service_facts_hash,
        )

    def plan_action(
        self, run_id: str, arguments: BashInput, *, action_id: str
    ) -> CommandActionPlan:
        facts = classify_argv(arguments.argv)
        cwd = self.normalized_cwd(arguments)
        normalized_cwd = str(cwd.relative_to(self.workspace).as_posix() or ".")
        payload = {
            "argv": list(arguments.argv),
            "cwd": normalized_cwd,
            "timeout_seconds": arguments.timeout_seconds,
        }
        input_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CommandActionPlan(
            action_id=action_id,
            run_id=run_id,
            argv=arguments.argv,
            cwd=normalized_cwd,
            executable=str(facts["executable"]),
            risk_level=facts["risk_level"],
            writes_workspace=bool(facts["writes"]),
            input_hash=input_hash,
            policy_hash="0" * 64,
        )

    def execute(self, arguments: BashInput) -> ToolResult:
        return self._execute(arguments, apple_ios_build_services=False)

    def execute_approved(
        self, arguments: BashInput, *, apple_ios_build_services: bool = False
    ) -> ToolResult:
        if apple_ios_build_services and not requests_approved_ios_build(arguments.argv):
            return ToolResult(ok=False, error_code="sandbox_apple_build_service_unsupported")
        return self._execute(arguments, apple_ios_build_services=apple_ios_build_services)

    def _execute(self, arguments: BashInput, *, apple_ios_build_services: bool) -> ToolResult:
        try:
            cwd = self.normalized_cwd(arguments)
        except ValueError as exc:
            return ToolResult(ok=False, error_code=str(exc))
        environment = build_child_environment(purpose="bash", source=self.environment_source)
        result = self.supervisor.run(
            ProcessRequest(
                argv=arguments.argv,
                cwd=cwd,
                env=environment.values,
                timeout_seconds=arguments.timeout_seconds,
                max_output_bytes=self.max_output_bytes,
                apple_ios_build_services=apple_ios_build_services,
            )
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        error_code: str | None = None
        ok = result.status == "exited" and result.exit_code == 0
        if result.status == "timed_out":
            error_code = "timeout"
        elif result.status == "cancelled":
            error_code = "cancelled"
        elif result.status == "error":
            error_code = "process_error"
        elif result.status == "exited" and result.exit_code != 0:
            error_code = "process_exit"
        if result.cleanup_error is not None:
            error_code = result.cleanup_error
        content = {
            "status": result.status,
            "exit_code": result.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "cwd": str(cwd.relative_to(self.workspace).as_posix() or "."),
            "argv": list(result.effective_argv or arguments.argv),
        }
        if apple_ios_build_services:
            content["system_service_side_effects_possible"] = True
            content["requested_argv"] = list(arguments.argv)
            content["build_artifacts"] = (
                "discarded" if result.cleanup_error is None else "cleanup_failed"
            )
        return ToolResult(
            ok=ok,
            truncated=result.stdout_truncated or result.stderr_truncated,
            error_code=error_code,
            content=content,
        )

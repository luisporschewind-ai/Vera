"""Single dependency assembly point for the CLI."""

import json
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from vera.config import VeraConfig, load_config, load_provider_environment
from vera.models.base import ModelAdapter
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.recovery.coordinator import RecoveryCoordinator
from vera.runtime.engine import VeraRuntime
from vera.tools.builtin import ListDirectoryTool, ReadFileTool, SearchTextTool
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


@dataclass(frozen=True)
class RuntimeDependencies:
    runtime: VeraRuntime
    config: VeraConfig


type RuntimeBuilder = Callable[[Path, str | None], RuntimeDependencies]


def load_or_create_installation_id(state_dir: Path) -> str:
    path = state_dir / "installation.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            installation_id = str(payload["installation_id"])
            if installation_id:
                return installation_id
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    state_dir.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(state_dir, 0o700)
    installation_id = uuid4().hex
    temporary = state_dir / "installation.json.tmp"
    body = json.dumps(
        {"installation_id": installation_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    return installation_id


def build_runtime(workspace: Path, model_profile: str | None = None) -> RuntimeDependencies:
    load_provider_environment()
    config = load_config(workspace, {})
    profile = model_profile or next(iter(config.providers), None)
    if profile is None or profile not in config.providers:
        raise ValueError("no model provider configured")
    provider = config.providers[profile]
    adapter: ModelAdapter = OpenAICompatibleAdapter(provider)
    paths = WorkspacePaths(workspace)
    registry = ToolRegistry()
    registry.register(ReadFileTool(paths, config.limits.max_file_bytes))
    registry.register(ListDirectoryTool(paths))
    registry.register(SearchTextTool(paths))
    policy = CommandPolicy(config.user_allowed_command_prefixes)
    installation_id = load_or_create_installation_id(config.state_dir)
    snapshot_store = RecoverySnapshotStore(config.state_dir)
    coordinator = RecoveryCoordinator(
        config.state_dir,
        installation_id,
        snapshot_store=snapshot_store,
    )
    runtime = VeraRuntime(
        adapter,
        registry,
        config.state_dir,
        config.limits,
        command_policy=policy,
        snapshot_store=snapshot_store,
        installation_id=installation_id,
        recovery_coordinator=coordinator,
    )
    return RuntimeDependencies(runtime=runtime, config=config)

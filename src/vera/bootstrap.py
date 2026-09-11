"""Single dependency assembly point for the CLI."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vera.config import VeraConfig, load_config, load_provider_environment
from vera.models.base import ModelAdapter
from vera.models.openai_compatible import OpenAICompatibleAdapter
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
    runtime = VeraRuntime(
        adapter,
        registry,
        config.state_dir,
        config.limits,
        command_policy=policy,
    )
    return RuntimeDependencies(runtime=runtime, config=config)

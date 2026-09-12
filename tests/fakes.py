"""Test doubles and representative-project case factory."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.tools.builtin import ReadFileTool
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths

__all__ = [
    "FakeModelAdapter",
    "PROJECT_KINDS",
    "RepresentativeProject",
    "allowed_python_policy",
    "copy_representative_project",
    "project_registry",
    "python_verify_argv",
    "tool_registry_for",
    "turns_for",
]

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "projects"
VERIFY_HELPER = PROJECT_FIXTURES / "_helpers" / "verify.py"
PROJECT_KINDS = ("swift", "python", "typescript")
EDIT_MARKER = "vera-edited"


@dataclass(frozen=True)
class RepresentativeProject:
    kind: str
    fixture_name: str
    read_path: str
    single_path: str
    single_after: str
    extra_path: str
    extra_after: str
    conversation: str

    @property
    def fixture_root(self) -> Path:
        return PROJECT_FIXTURES / self.fixture_name


def project_registry() -> dict[str, RepresentativeProject]:
    return {
        "swift": RepresentativeProject(
            kind="swift",
            fixture_name="swift-minimal",
            read_path="Demo/ViewController.swift",
            single_path="Demo/ViewController.swift",
            single_after=(
                'import Foundation\n\nenum DemoGreeting {\n    static let text = "vera-edited"\n}\n'
            ),
            extra_path="Demo/Helper.swift",
            extra_after="enum DemoHelper { static let ok = true }\n",
            conversation="This Swift fixture exposes DemoGreeting.text.",
        ),
        "python": RepresentativeProject(
            kind="python",
            fixture_name="python-minimal",
            read_path="src/demo/__init__.py",
            single_path="src/demo/__init__.py",
            single_after='def greeting() -> str:\n    return "vera-edited"\n',
            extra_path="src/demo/extra.py",
            extra_after="VALUE = 1\n",
            conversation="This Python package exposes greeting().",
        ),
        "typescript": RepresentativeProject(
            kind="typescript",
            fixture_name="typescript-minimal",
            read_path="src/index.ts",
            single_path="src/index.ts",
            single_after='export const greeting = "vera-edited";\n',
            extra_path="src/extra.ts",
            extra_after="export const extra = true;\n",
            conversation="This TypeScript module exports greeting.",
        ),
    }


def copy_representative_project(kind: str, destination: Path) -> RepresentativeProject:
    project = project_registry()[kind]
    shutil.copytree(project.fixture_root, destination, dirs_exist_ok=True)
    return project


def python_verify_argv(needle: str, relative_path: str) -> list[str]:
    return [sys.executable, str(VERIFY_HELPER), needle, relative_path]


def tool_registry_for(workspace: Path) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool(WorkspacePaths(workspace), 1_000_000))
    return registry


def allowed_python_policy() -> CommandPolicy:
    return CommandPolicy(user_allowed_prefixes=((sys.executable,),))


def _change(
    path: str,
    after: str,
    *,
    operation: str = "update",
    verification: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary": f"{operation} {path}",
        "changes": [{"operation": operation, "path": path, "after_content": after}],
    }
    if verification is not None:
        payload["verification"] = verification
    return payload


def turns_for(project: RepresentativeProject, scenario: str) -> list[ModelTurn]:
    if scenario == "readonly":
        return [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="read_file",
                        arguments={"path": project.read_path},
                    ),
                ),
            ),
            ModelTurn(assistant_text=project.conversation, finish_reason="stop"),
        ]
    if scenario == "single":
        return [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments=_change(project.single_path, project.single_after),
                    ),
                ),
            )
        ]
    if scenario == "multi":
        return [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments={
                            "summary": "multi-file edit",
                            "changes": [
                                {
                                    "operation": "update",
                                    "path": project.single_path,
                                    "after_content": project.single_after,
                                },
                                {
                                    "operation": "create",
                                    "path": project.extra_path,
                                    "after_content": project.extra_after,
                                },
                            ],
                        },
                    ),
                ),
            )
        ]
    if scenario in {"reject", "cancel", "interrupt"}:
        return turns_for(project, "single")
    if scenario == "verify_ok":
        return [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments=_change(
                            project.single_path,
                            project.single_after,
                            verification=[
                                {
                                    "argv": python_verify_argv(EDIT_MARKER, project.single_path),
                                    "cwd": ".",
                                }
                            ],
                        ),
                    ),
                ),
            )
        ]
    if scenario == "verify_fail":
        return [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments=_change(
                            project.single_path,
                            project.single_after,
                            verification=[
                                {
                                    "argv": python_verify_argv(
                                        "missing-marker", project.single_path
                                    ),
                                    "cwd": ".",
                                }
                            ],
                        ),
                    ),
                ),
            )
        ]
    if scenario == "escape":
        return [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments=_change("../outside.txt", "escaped\n", operation="create"),
                    ),
                ),
            )
        ]
    if scenario == "dangerous":
        return [
            ModelTurn(
                finish_reason="tool_calls",
                tool_calls=(
                    ModelToolCall(
                        call_id="1",
                        name="propose_changeset",
                        arguments=_change(
                            project.single_path,
                            project.single_after,
                            verification=[{"argv": ["rm", "-rf", "."], "cwd": "."}],
                        ),
                    ),
                ),
            )
        ]
    raise KeyError(scenario)

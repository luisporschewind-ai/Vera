"""Workspace-root project instruction discovery. Advisory only."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vera.contracts.changes import ChangeSet

ProjectInstructionName = Literal["AGENTS.md", "VERA.md"]

FILE_LIMIT = 32_768
TOTAL_LIMIT = 65_536
_PRIORITIES: dict[ProjectInstructionName, int] = {"AGENTS.md": 10, "VERA.md": 20}
_NAMES: tuple[ProjectInstructionName, ...] = ("AGENTS.md", "VERA.md")


@dataclass(frozen=True)
class ProjectInstructionSource:
    name: ProjectInstructionName
    content: str
    content_hash: str
    byte_count: int
    priority: int


@dataclass(frozen=True)
class ProjectInstructionIssue:
    name: ProjectInstructionName
    reason_code: Literal[
        "unsafe_file_type",
        "invalid_encoding",
        "size_limit_exceeded",
        "file_changed_during_read",
        "read_failed",
    ]


@dataclass(frozen=True)
class ProjectInstructionSet:
    sources: tuple[ProjectInstructionSource, ...]
    issues: tuple[ProjectInstructionIssue, ...]
    guidance_hash: str


def _empty_hash() -> str:
    return hashlib.sha256(b"").hexdigest()


def _guidance_hash(sources: tuple[ProjectInstructionSource, ...]) -> str:
    digest = hashlib.sha256()
    for item in sources:
        digest.update(item.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.content.encode("utf-8"))
    return digest.hexdigest() if sources else _empty_hash()


def public_source_facts(source: ProjectInstructionSource) -> dict[str, object]:
    return {
        "name": source.name,
        "priority": source.priority,
        "content_hash": source.content_hash,
        "byte_count": source.byte_count,
    }


def public_issue_facts(issue: ProjectInstructionIssue) -> dict[str, object]:
    return {"name": issue.name, "reason_code": issue.reason_code}


def public_instruction_facts(loaded: ProjectInstructionSet) -> dict[str, object]:
    return {
        "guidance_hash": loaded.guidance_hash,
        "sources": [public_source_facts(item) for item in loaded.sources],
        "issues": [public_issue_facts(item) for item in loaded.issues],
    }


def format_instruction_status(payload: dict[str, object]) -> str:
    sources = payload.get("sources")
    issues = payload.get("issues")
    lines: list[str] = []
    source_items = sources if isinstance(sources, list) else []
    issue_items = issues if isinstance(issues, list) else []
    if not source_items and not issue_items:
        lines.append("未发现项目指令")
    for item in source_items:
        if not isinstance(item, dict):
            continue
        digest = str(item.get("content_hash") or "")
        lines.append(
            f"已加载 {item.get('name')} 优先级 {item.get('priority')} "
            f"{digest[:12]} {item.get('byte_count')} bytes"
        )
    for item in issue_items:
        if not isinstance(item, dict):
            continue
        lines.append(f"已跳过 {item.get('name')} {item.get('reason_code')}")
    run_hash = payload.get("run_guidance_hash")
    if isinstance(run_hash, str) and run_hash:
        lines.append(f"当前 Run {run_hash[:12]}")
    if payload.get("pending_next_run"):
        lines.append("下个 Run 生效")
    return "\n".join(lines)


def _same_stat(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
    )


class ProjectInstructionService:
    def load(self, workspace_root: Path) -> ProjectInstructionSet:
        root = workspace_root.expanduser().resolve()
        sources: list[ProjectInstructionSource] = []
        issues: list[ProjectInstructionIssue] = []
        total = 0
        for name in _NAMES:
            loaded, issue = self._read_one(root, name)
            if issue is not None:
                issues.append(issue)
                continue
            if loaded is None:
                continue
            if total + loaded.byte_count > TOTAL_LIMIT:
                issues.append(ProjectInstructionIssue(name=name, reason_code="size_limit_exceeded"))
                continue
            total += loaded.byte_count
            sources.append(loaded)
        ordered = tuple(sorted(sources, key=lambda item: item.priority))
        return ProjectInstructionSet(
            sources=ordered,
            issues=tuple(issues),
            guidance_hash=_guidance_hash(ordered),
        )

    def validate_init_changeset(self, change_set: ChangeSet) -> None:
        files = change_set.files
        if (
            len(files) != 1
            or files[0].path != "VERA.md"
            or files[0].operation not in {"create", "update"}
            or change_set.verification
        ):
            raise ValueError("project_init_scope_violation")

    def _read_one(
        self, root: Path, name: ProjectInstructionName
    ) -> tuple[ProjectInstructionSource | None, ProjectInstructionIssue | None]:
        path = root / name
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return None, None
        except OSError:
            return None, ProjectInstructionIssue(name=name, reason_code="read_failed")
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None, ProjectInstructionIssue(name=name, reason_code="unsafe_file_type")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except OSError:
            return None, ProjectInstructionIssue(name=name, reason_code="read_failed")
        try:
            first = os.fstat(fd)
            if first.st_size > FILE_LIMIT:
                return None, ProjectInstructionIssue(name=name, reason_code="size_limit_exceeded")
            payload = os.read(fd, FILE_LIMIT + 1)
            second = os.fstat(fd)
        except OSError:
            return None, ProjectInstructionIssue(name=name, reason_code="read_failed")
        finally:
            os.close(fd)
        if not _same_stat(info, first) or not _same_stat(first, second):
            return None, ProjectInstructionIssue(name=name, reason_code="file_changed_during_read")
        if len(payload) > FILE_LIMIT:
            return None, ProjectInstructionIssue(name=name, reason_code="size_limit_exceeded")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None, ProjectInstructionIssue(name=name, reason_code="invalid_encoding")
        digest = hashlib.sha256(payload).hexdigest()
        return (
            ProjectInstructionSource(
                name=name,
                content=text,
                content_hash=digest,
                byte_count=len(payload),
                priority=_PRIORITIES[name],
            ),
            None,
        )

"""Bounded facts for repository hooks and existing signing configuration."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Literal, cast

from vera.contracts import ContractModel
from vera.git.service import GitService, GitServiceError

_COMMIT_HOOKS = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit")


class GitHookEntry(ContractModel):
    name: str
    relative_path: str
    content_hash: str
    executable: bool


class GitHookFacts(ContractModel):
    hooks_path: str
    hooks: tuple[GitHookEntry, ...]
    facts_hash: str


class GitSigningFacts(ContractModel):
    configured: bool
    format: Literal["openpgp", "ssh", "x509"] | None = None
    key_configured: bool = False
    facts_hash: str


class GitHookInspector:
    def __init__(self, service: GitService) -> None:
        self.service = service

    def inspect(self) -> GitHookFacts:
        hooks_path = self._hooks_path()
        entries: list[GitHookEntry] = []
        if hooks_path.is_dir():
            for name in _COMMIT_HOOKS:
                candidate = hooks_path / name
                try:
                    details = candidate.lstat()
                    content = candidate.read_bytes()
                except OSError:
                    continue
                if not stat.S_ISREG(details.st_mode) and not stat.S_ISLNK(details.st_mode):
                    continue
                entries.append(
                    GitHookEntry(
                        name=name,
                        relative_path=self._relative_path(candidate),
                        content_hash=hashlib.sha256(content).hexdigest(),
                        executable=stat.S_ISREG(details.st_mode)
                        and bool(details.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)),
                    )
                )
        hooks = tuple(entries)
        facts_hash = _digest(
            {
                "hooks_path": str(hooks_path),
                "hooks": [entry.model_dump(mode="json") for entry in hooks],
            }
        )
        return GitHookFacts(
            hooks_path=str(hooks_path),
            hooks=hooks,
            facts_hash=facts_hash,
        )

    def signing_facts(self) -> GitSigningFacts:
        enabled = self._config("commit.gpgSign").casefold() in {"true", "yes", "on", "1"}
        configured_format = self._config("gpg.format") or None
        signing_key = self._config("user.signingKey") or self._config("gpg.ssh.defaultKeyCommand")
        format_name: Literal["openpgp", "ssh", "x509"] | None = (
            cast(Literal["openpgp", "ssh", "x509"], configured_format)
            if configured_format in {"openpgp", "ssh", "x509"}
            else None
        )
        configured = enabled or format_name is not None or signing_key is not None
        return GitSigningFacts(
            configured=configured,
            format=format_name,
            key_configured=signing_key is not None,
            facts_hash=_digest(
                {
                    "configured": configured,
                    "format": format_name,
                    "key_configured": signing_key is not None,
                }
            ),
        )

    def _hooks_path(self) -> Path:
        try:
            result = self.service._run(("rev-parse", "--git-path", "hooks"))
        except GitServiceError as exc:
            raise GitServiceError("git_hook_facts_unavailable") from exc
        raw = result.stdout.decode("utf-8", errors="strict").strip()
        path = Path(raw)
        if not path.is_absolute():
            path = self.service.repository.repository_root / path
        return path.resolve()

    def _relative_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.service.repository.repository_root).as_posix()
        except ValueError:
            return str(path)

    def _config(self, key: str) -> str:
        try:
            result = self.service._run(("config", "--get", key))
        except GitServiceError as exc:
            if exc.code == "git_command_failed":
                return ""
            raise
        return result.stdout.decode("utf-8", errors="replace").strip()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()

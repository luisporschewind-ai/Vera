"""Build deterministic, reviewable change sets from workspace proposals."""

import difflib
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from vera.contracts import ContractModel
from vera.contracts.changes import ChangeSet, FileChange
from vera.contracts.verification import VerificationCommand
from vera.workspace.paths import PathFact, WorkspaceBoundaryError, WorkspacePaths

ABSENT_HASH = "0" * 64


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class ChangeProposal(ContractModel):
    operation: Literal["create", "update", "delete"]
    path: str
    after_content: str | None = None


class BuiltChangeSet(ContractModel):
    change_set: ChangeSet
    intended_bytes: dict[str, bytes] = Field(default_factory=dict)
    path_facts: dict[str, PathFact] = Field(default_factory=dict)

    def facts_digest(self) -> str:
        payload = {path: fact.digest() for path, fact in sorted(self.path_facts.items())}
        return sha256_bytes(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        )


class ChangeSetBuilder:
    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths

    @staticmethod
    def _diff(path: str, before: bytes, after: bytes) -> str:
        before_text = before.decode("utf-8")
        after_text = after.decode("utf-8")
        return "".join(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )

    def build(
        self,
        run_id: str,
        summary: str,
        proposals: Sequence[ChangeProposal],
        verification: Sequence[VerificationCommand],
    ) -> BuiltChangeSet:
        ordered = sorted(proposals, key=lambda item: item.path)
        if len({item.path for item in ordered}) != len(ordered):
            raise ValueError("duplicate change path")
        files: list[FileChange] = []
        intended: dict[str, bytes] = {}
        path_facts: dict[str, PathFact] = {}
        for proposal in ordered:
            try:
                fact = self.paths.inspect_mutation(proposal.path)
            except WorkspaceBoundaryError:
                raise
            target = Path(fact.canonical_path)
            exists = fact.exists
            if proposal.operation == "create":
                if exists or proposal.after_content is None:
                    raise ValueError("create requires an absent path and content")
                before = b""
                after = proposal.after_content.encode("utf-8")
            elif proposal.operation == "update":
                if not exists or fact.kind != "regular" or proposal.after_content is None:
                    raise ValueError("update requires an existing text file and content")
                before = target.read_bytes()
                before.decode("utf-8")
                after = proposal.after_content.encode("utf-8")
            else:
                if not exists or fact.kind != "regular" or proposal.after_content is not None:
                    raise ValueError("delete requires an existing file and no content")
                before = target.read_bytes()
                before.decode("utf-8")
                after = b""
            before_hash = ABSENT_HASH if proposal.operation == "create" else sha256_bytes(before)
            after_hash = ABSENT_HASH if proposal.operation == "delete" else sha256_bytes(after)
            files.append(
                FileChange(
                    operation=proposal.operation,
                    path=proposal.path,
                    before_hash=before_hash,
                    after_hash=after_hash,
                    unified_diff=self._diff(proposal.path, before, after),
                )
            )
            if proposal.operation != "delete":
                intended[proposal.path] = after
            path_facts[proposal.path] = fact
        hash_payload = {
            "files": [item.model_dump(mode="json") for item in files],
            # Planned argv, profile, and external root are part of the reviewable hash.
            "verification": [item.model_dump(mode="json") for item in verification],
        }
        content_hash = sha256_bytes(
            json.dumps(
                hash_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        change_set = ChangeSet(
            changeset_id=f"cs_{uuid4().hex}",
            run_id=run_id,
            summary=summary,
            files=tuple(files),
            verification=tuple(verification),
            content_hash=content_hash,
        )
        return BuiltChangeSet(
            change_set=change_set,
            intended_bytes=intended,
            path_facts=path_facts,
        )

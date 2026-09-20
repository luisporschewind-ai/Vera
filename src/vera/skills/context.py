"""Restricted Context assembly from immutable Skill snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from vera.content.envelope import ContentEnvelope, build_content_envelope
from vera.content.trust import ContentTrustLevel
from vera.skills.models import FrozenSkillSnapshot

MAX_CONTEXT_BYTES = 128 * 1024


class SkillContextError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class SkillContextPart:
    envelope: ContentEnvelope
    text: str


class SkillContextAssembler:
    def assemble(self, snapshot: FrozenSkillSnapshot) -> tuple[SkillContextPart, ...]:
        total = 0
        parts: list[SkillContextPart] = []
        trust = (
            ContentTrustLevel.UNTRUSTED
            if snapshot.snapshot.source_kind == "workspace"
            else ContentTrustLevel.ADVISORY
        )
        for item in sorted(snapshot.files, key=lambda file: file.relative_path):
            text = item.content.decode("utf-8")
            total += len(item.content)
            if total > MAX_CONTEXT_BYTES:
                raise SkillContextError(
                    "skill_package_limit_exceeded", "Skill Context exceeds 128 KiB"
                )
            envelope = build_content_envelope(
                text,
                source_kind="skill_content",
                origin=f"{snapshot.snapshot.skill_id}:{item.relative_path}",
            ).model_copy(update={"trust_level": trust})
            parts.append(SkillContextPart(envelope=envelope, text=text))
        return tuple(parts)

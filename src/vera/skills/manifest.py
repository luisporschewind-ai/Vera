"""Strict, bounded parsing of the v1 local Skill package format."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tomllib
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from vera import __version__
from vera.contracts.skills import SkillAvailability, SkillSourceKind, SkillSummary
from vera.skills.models import ParsedSkillPackage, SkillFile

MAX_FILES = 32
MAX_FILE_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 128 * 1024
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillValidationError(ValueError):
    """Stable validation failure that can be projected without private paths."""

    def __init__(self, code: str, message: str, *, metadata: dict[str, str] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.metadata = dict(metadata or {})


class SkillCompatibility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_vera_core: str
    max_vera_core_exclusive: str | None = None

    @field_validator("min_vera_core", "max_vera_core_exclusive")
    @classmethod
    def valid_semver(cls, value: str | None) -> str | None:
        if value is not None and _SEMVER.fullmatch(value) is None:
            raise ValueError("invalid semver")
        return value

    @model_validator(mode="after")
    def ordered_bounds(self) -> SkillCompatibility:
        if self.max_vera_core_exclusive is not None and _version_key(
            self.min_vera_core
        ) >= _version_key(self.max_vera_core_exclusive):
            raise ValueError("invalid compatibility range")
        return self


class SkillResources(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    references: tuple[str, ...] = ()
    templates: tuple[str, ...] = ()


class SkillManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: Literal[1] = 1
    name: str
    version: str
    description: str
    compatibility: SkillCompatibility
    resources: SkillResources = Field(default_factory=SkillResources)

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        if _NAME.fullmatch(value) is None:
            raise ValueError("name must be lower kebab-case")
        return value

    @field_validator("version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if _SEMVER.fullmatch(value) is None:
            raise ValueError("version must be strict semver")
        return value

    @field_validator("description")
    @classmethod
    def nonempty_description(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("description must be non-empty")
        return value


def _version_key(value: str) -> tuple[int, int, int, str]:
    match = _SEMVER.fullmatch(value)
    if match is None:
        raise ValueError("invalid semver")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4) or "")


def _trust_for(source_kind: SkillSourceKind) -> Literal["advisory", "untrusted"]:
    return "untrusted" if source_kind == "workspace" else "advisory"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_files(files: tuple[SkillFile, ...]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(item.content).to_bytes(8, "big"))
        digest.update(item.content)
    return digest.hexdigest()


def _safe_regular_file(path: Path) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise SkillValidationError("skill_resource_missing", str(path)) from exc
    except OSError as exc:
        raise SkillValidationError(
            "skill_resource_invalid", "cannot inspect Skill resource"
        ) from exc
    if stat.S_ISLNK(info.st_mode):
        raise SkillValidationError("skill_symlink_refused", "Skill resources cannot be symlinks")
    if not stat.S_ISREG(info.st_mode):
        raise SkillValidationError(
            "skill_resource_invalid", "Skill resources must be regular files"
        )
    return info


def _read_utf8(path: Path, *, missing_code: str) -> bytes:
    try:
        info = _safe_regular_file(path)
    except SkillValidationError as exc:
        if exc.code == "skill_resource_missing":
            raise SkillValidationError(missing_code, "required Skill file is missing") from exc
        raise
    if info.st_size > MAX_FILE_BYTES:
        raise SkillValidationError("skill_package_limit_exceeded", "Skill file exceeds 64 KiB")
    try:
        payload = path.read_bytes()
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillValidationError("skill_resource_invalid", "Skill file is not UTF-8") from exc
    except OSError as exc:
        raise SkillValidationError("skill_resource_invalid", "cannot read Skill file") from exc
    if len(payload) > MAX_FILE_BYTES:
        raise SkillValidationError("skill_package_limit_exceeded", "Skill file exceeds 64 KiB")
    return payload


def _resource_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        raise SkillValidationError("skill_path_escape", "resource path is not a safe POSIX path")
    path = PurePosixPath(raw)
    if (
        raw.startswith("/")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise SkillValidationError("skill_path_escape", "resource path escapes the Skill package")
    normalized = "/".join(path.parts)
    if normalized != raw or len(path.parts) < 2 or path.parts[0] not in {"references", "templates"}:
        raise SkillValidationError(
            "skill_resource_invalid", "resource path must be declared below references/templates"
        )
    return normalized


class ManifestLoader:
    def __init__(self, *, core_version: str = __version__) -> None:
        if _SEMVER.fullmatch(core_version) is None:
            raise ValueError("core_version must be strict semver")
        self._core_version = core_version

    def load(self, package_root: Path, *, source_kind: SkillSourceKind) -> ParsedSkillPackage:
        package_root = Path(package_root)
        try:
            root_info = os.lstat(package_root)
        except OSError as exc:
            raise SkillValidationError(
                "skill_manifest_missing", "Skill package is missing"
            ) from exc
        if stat.S_ISLNK(root_info.st_mode):
            raise SkillValidationError("skill_symlink_refused", "Skill package cannot be a symlink")
        if not stat.S_ISDIR(root_info.st_mode):
            raise SkillValidationError(
                "skill_manifest_invalid", "Skill package must be a directory"
            )

        manifest_path = package_root / "skill.toml"
        try:
            manifest_bytes = _read_utf8(manifest_path, missing_code="skill_manifest_missing")
            raw = tomllib.loads(manifest_bytes.decode("utf-8"))
        except SkillValidationError:
            raise
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise SkillValidationError("skill_manifest_invalid", "skill.toml is invalid") from exc
        try:
            manifest = SkillManifest.model_validate(raw)
        except ValidationError as exc:
            raw_format = raw.get("format_version") if isinstance(raw, dict) else None
            code = (
                "skill_manifest_version_unsupported"
                if raw_format not in (None, 1)
                else "skill_manifest_invalid"
            )
            raise SkillValidationError(code, "skill.toml does not match the v1 schema") from exc

        manifest_hash = _sha256(_canonical_json(manifest.model_dump(mode="json")))
        metadata = {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "manifest_hash": manifest_hash,
        }
        if not self._compatible(manifest.compatibility):
            raise SkillValidationError(
                "skill_version_incompatible",
                "Skill is not compatible with this Vera Core",
                metadata=metadata,
            )

        declared: list[tuple[str, Literal["reference", "template"]]] = []
        for item in manifest.resources.references:
            declared.append((_resource_path(item), "reference"))
        for item in manifest.resources.templates:
            declared.append((_resource_path(item), "template"))
        paths = [item[0] for item in declared]
        if len(paths) != len(set(paths)):
            raise SkillValidationError("skill_resource_invalid", "resource paths must be unique")
        if 2 + len(declared) > MAX_FILES:
            raise SkillValidationError(
                "skill_package_limit_exceeded", "Skill package has too many files"
            )

        files = [
            SkillFile(
                relative_path="SKILL.md",
                kind="entry",
                content=_read_utf8(
                    package_root / "SKILL.md", missing_code="skill_manifest_missing"
                ),
                content_hash="",
            )
        ]
        for relative_path, kind in declared:
            files.append(
                SkillFile(
                    relative_path=relative_path,
                    kind=kind,
                    content=_read_utf8(
                        package_root / Path(*relative_path.split("/")),
                        missing_code="skill_resource_missing",
                    ),
                    content_hash="",
                )
            )
        normalized_files = tuple(
            item.__class__(
                relative_path=item.relative_path,
                kind=item.kind,
                content=item.content,
                content_hash=_sha256(item.content),
            )
            for item in files
        )
        total = len(manifest_bytes) + sum(len(item.content) for item in normalized_files)
        if total > MAX_PACKAGE_BYTES:
            raise SkillValidationError(
                "skill_package_limit_exceeded", "Skill package exceeds 128 KiB"
            )
        resource_hash = _hash_files(normalized_files)
        package_hash = _sha256(manifest_bytes + bytes.fromhex(resource_hash))
        return ParsedSkillPackage(
            package_root=package_root,
            source_kind=source_kind,
            skill_id=f"{source_kind}:{manifest.name}",
            manifest=manifest,
            manifest_hash=manifest_hash,
            files=normalized_files,
            resource_hash=resource_hash,
            package_hash=package_hash,
        )

    def _compatible(self, compatibility: SkillCompatibility) -> bool:
        current = _version_key(self._core_version)
        if current < _version_key(compatibility.min_vera_core):
            return False
        if compatibility.max_vera_core_exclusive is not None and current >= _version_key(
            compatibility.max_vera_core_exclusive
        ):
            return False
        return not (
            compatibility.max_vera_core_exclusive is not None
            and current >= _version_key(compatibility.max_vera_core_exclusive)
        )


def summary_for_package(
    package: ParsedSkillPackage,
    *,
    availability: Literal["available", "conflict"] = "available",
    reason_codes: tuple[str, ...] = (),
) -> SkillSummary:
    return SkillSummary(
        skill_id=package.skill_id,
        name=package.manifest.name,
        version=package.manifest.version,
        description=package.manifest.description,
        source_kind=package.source_kind,
        trust_level=_trust_for(package.source_kind),
        availability=availability,
        manifest_hash=package.manifest_hash,
        resource_hash=package.resource_hash,
        reason_codes=reason_codes,
    )


def summary_for_error(source_kind: SkillSourceKind, error: SkillValidationError) -> SkillSummary:
    availability: SkillAvailability = (
        "incompatible" if error.code == "skill_version_incompatible" else "invalid"
    )
    return SkillSummary(
        name=error.metadata.get("name"),
        version=error.metadata.get("version"),
        description=error.metadata.get("description"),
        skill_id=(
            f"{source_kind}:{error.metadata['name']}" if error.metadata.get("name") else None
        ),
        source_kind=source_kind,
        trust_level=_trust_for(source_kind),
        availability=availability,
        manifest_hash=error.metadata.get("manifest_hash"),
        reason_codes=(error.code,),
    )

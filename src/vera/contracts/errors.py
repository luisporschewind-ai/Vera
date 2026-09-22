"""Stable Core error codes shared by persistence, workspace, and recovery."""

from __future__ import annotations

import errno
from enum import StrEnum


class CoreErrorCode(StrEnum):
    TRUNCATED_TAIL = "truncated_tail"
    MID_FILE_CORRUPT = "mid_file_corrupt"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    UNSUPPORTED_VERSION = "unsupported_version"
    MISSING_FIELD = "missing_field"
    UNEXPECTED_FIELD = "unexpected_field"
    NO_SPACE = "no_space"
    PERMISSION_DENIED = "permission_denied"
    READ_ONLY_FILESYSTEM = "read_only_filesystem"
    INVALID_ENCODING = "invalid_encoding"
    WRITE_INTERRUPTED = "write_interrupted"
    WRITE_FAILED = "write_failed"
    FILE_BUSY = "file_busy"
    SKILL_NOT_FOUND = "skill_not_found"
    SKILL_MANIFEST_MISSING = "skill_manifest_missing"
    SKILL_MANIFEST_INVALID = "skill_manifest_invalid"
    SKILL_MANIFEST_VERSION_UNSUPPORTED = "skill_manifest_version_unsupported"
    SKILL_VERSION_INCOMPATIBLE = "skill_version_incompatible"
    SKILL_NAME_CONFLICT = "skill_name_conflict"
    SKILL_PATH_ESCAPE = "skill_path_escape"
    SKILL_SYMLINK_REFUSED = "skill_symlink_refused"
    SKILL_RESOURCE_MISSING = "skill_resource_missing"
    SKILL_RESOURCE_INVALID = "skill_resource_invalid"
    SKILL_PACKAGE_LIMIT_EXCEEDED = "skill_package_limit_exceeded"
    SKILL_SOURCE_CHANGED = "skill_source_changed"
    SKILL_SELECTION_INVALID = "skill_selection_invalid"
    SKILL_SNAPSHOT_WRITE_FAILED = "skill_snapshot_write_failed"
    SKILL_SNAPSHOT_MISSING = "skill_snapshot_missing"
    SKILL_SNAPSHOT_CORRUPT = "skill_snapshot_corrupt"
    SKILL_SNAPSHOT_VERSION_UNSUPPORTED = "skill_snapshot_version_unsupported"
    SKILL_SNAPSHOT_CLEANUP_REFUSED = "skill_snapshot_cleanup_refused"


_ERRNO_CODES: dict[int, CoreErrorCode] = {
    errno.ENOSPC: CoreErrorCode.NO_SPACE,
    errno.EACCES: CoreErrorCode.PERMISSION_DENIED,
    errno.EPERM: CoreErrorCode.PERMISSION_DENIED,
    errno.EROFS: CoreErrorCode.READ_ONLY_FILESYSTEM,
    errno.EIO: CoreErrorCode.WRITE_INTERRUPTED,
    errno.EINTR: CoreErrorCode.WRITE_INTERRUPTED,
    errno.EBUSY: CoreErrorCode.FILE_BUSY,
    errno.ETXTBSY: CoreErrorCode.FILE_BUSY,
}
if hasattr(errno, "EDQUOT"):
    _ERRNO_CODES[errno.EDQUOT] = CoreErrorCode.NO_SPACE


def classify_os_error(exc: BaseException) -> str:
    """Map an OS-level write/read failure to a stable Core error code."""

    if isinstance(exc, UnicodeDecodeError):
        return CoreErrorCode.INVALID_ENCODING.value
    if not isinstance(exc, OSError):
        return CoreErrorCode.WRITE_FAILED.value
    errno_value = exc.errno
    if errno_value is None:
        return CoreErrorCode.WRITE_FAILED.value
    return _ERRNO_CODES.get(errno_value, CoreErrorCode.WRITE_FAILED).value

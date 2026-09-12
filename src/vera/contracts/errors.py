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

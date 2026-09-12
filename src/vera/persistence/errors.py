"""State format version errors for private persistence codecs."""

from __future__ import annotations

from vera.contracts.errors import CoreErrorCode

_DEFAULT_ADVICE: dict[str, str] = {
    CoreErrorCode.TRUNCATED_TAIL.value: "已忽略未提交的尾记录；已提交事件可继续读取。",
    CoreErrorCode.MID_FILE_CORRUPT.value: (
        "中间记录损坏。保留原文件，不要自动删除；必要时从 Checkpoint 恢复。"
    ),
    CoreErrorCode.CHECKSUM_MISMATCH.value: (
        "持久记录校验失败。保留原字节，核对 Checkpoint 与工作区。"
    ),
    CoreErrorCode.UNSUPPORTED_VERSION.value: "遇到未知版本。升级 Vera 或保留原数据，不要改写。",
    CoreErrorCode.MISSING_FIELD.value: "记录缺少必填字段。保留原文件并人工检查。",
    CoreErrorCode.UNEXPECTED_FIELD.value: "记录含未知或危险字段。拒绝加载并保留原字节。",
    CoreErrorCode.NO_SPACE.value: "磁盘空间不足，未覆盖旧状态。清理空间后重试。",
    CoreErrorCode.PERMISSION_DENIED.value: "目标不可写，未覆盖旧状态。检查目录权限。",
    CoreErrorCode.READ_ONLY_FILESYSTEM.value: "文件系统只读，未覆盖旧状态。",
    CoreErrorCode.INVALID_ENCODING.value: "编码无效。保留原文件，不要自动修复。",
    CoreErrorCode.WRITE_INTERRUPTED.value: "写入中断，未覆盖旧状态。检查磁盘后重试。",
    CoreErrorCode.WRITE_FAILED.value: "写入失败，未覆盖旧状态。检查权限与磁盘空间。",
    CoreErrorCode.FILE_BUSY.value: "文件被占用，未覆盖旧状态。关闭占用进程后重试。",
    "snapshot_write_failed": "恢复快照写入失败，未覆盖旧文件。检查权限与磁盘空间。",
    "invalid_snapshot": "恢复快照无法解析。保留原文件并人工检查。",
    "invalid_manifest": "Run manifest 无法解析。保留原文件并人工检查。",
    "migration_apply_failed": "迁移失败，已保留原始字节。不要删除 run 目录。",
    "missing_version": "缺少版本字段。保留原文件并人工检查。",
}


def default_advice(code: str) -> str:
    return _DEFAULT_ADVICE.get(code, "保留原始数据并人工处理，不要自动删除。")


class PersistenceFault(ValueError):
    """Fail-closed persistence error with a stable code and operator advice."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        advice: str | None = None,
        version: int | None = None,
        line: int | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.advice = advice if advice is not None else default_advice(code)
        self.version = version
        self.line = line


class StateVersionError(PersistenceFault):
    """Raised when private state uses an unsupported or missing format version."""

    def __init__(
        self,
        code: str,
        version: int | None = None,
        *,
        advice: str | None = None,
    ) -> None:
        super().__init__(code, version=version, advice=advice)


class JournalCorrupt(PersistenceFault):
    """Raised when a journal is malformed or its sequence is not continuous."""

    def __init__(
        self,
        message: str,
        *,
        code: str = CoreErrorCode.MID_FILE_CORRUPT.value,
        advice: str | None = None,
        line: int | None = None,
    ) -> None:
        super().__init__(code, message, advice=advice, line=line)

"""Shared constants for extracted SessionController flows."""

_TERMINAL_TYPES = frozenset(
    {
        "run.completed",
        "run.failed",
        "run.cancelled",
        "recovery.abandoned",
        "rollback.completed",
        "rollback.conflicted",
        "recovery.manual_required",
    }
)

_UNSAVED_ADVICE = (
    "会话记录写入失败。工作区与 Run 证据已保留；当前进程可继续使用本轮，"
    "但退出前请新建会话或从已保存前缀恢复。"
)

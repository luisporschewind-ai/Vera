"""Local doctor and redacted config views. Never print secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

from vera.config import VeraConfig
from vera.redaction import Redactor
from vera.session.status import WorkspaceStatusProbe
from vera.version import current_identity

CheckStatus = Literal["pass", "warning", "fail", "unavailable"]


def _item(name: str, status: CheckStatus, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def doctor_report(
    *,
    workspace: Path,
    state_dir: Path,
    user_config: Path | None,
    tty: bool | None = None,
    term: str | None = None,
) -> dict[str, Any]:
    is_tty = sys.stdout.isatty() if tty is None else tty
    term_value = os.environ.get("TERM", "") if term is None else term
    python_status: CheckStatus = "pass" if sys.version_info >= (3, 12) else "fail"
    terminal_ok = bool(is_tty and term_value and term_value != "dumb")
    terminal_status: CheckStatus = "pass" if terminal_ok else "warning"
    config_exists = user_config is not None and user_config.is_file()
    config_status: CheckStatus = "pass" if config_exists else "warning"
    state_status: CheckStatus = "unavailable"
    state_detail = "state directory missing"
    if state_dir.exists():
        mode = state_dir.stat().st_mode & 0o777
        if mode & 0o077:
            state_status = "fail"
            state_detail = f"state dir mode {oct(mode)} is too open"
        else:
            state_status = "pass"
            state_detail = f"mode {oct(mode)}"
    git = WorkspaceStatusProbe().inspect(workspace)
    git_status: CheckStatus = "pass" if git.available else "warning"
    try:
        version_detail = current_identity().doctor_detail()
        version_status: CheckStatus = "pass"
    except Exception:
        version_detail = "unavailable"
        version_status = "unavailable"
    items = (
        _item("version", version_status, version_detail),
        _item("python", python_status, f"{sys.version_info.major}.{sys.version_info.minor}"),
        _item("terminal", terminal_status, term_value or "unavailable"),
        _item(
            "config",
            config_status,
            str(user_config) if user_config is not None else "no user config file",
        ),
        _item("state_dir", state_status, state_detail),
        _item("git", git_status, git.branch or "not a repository"),
    )
    return {"items": list(items)}


def redacted_config_view(config: VeraConfig, sources: dict[str, str]) -> dict[str, Any]:
    redactor = Redactor([])
    providers: dict[str, Any] = {}
    for name, provider in config.providers.items():
        providers[name] = {
            "model": provider.model,
            "base_url": str(provider.base_url),
            "api_key_env": provider.api_key_env,
        }
    payload = {
        "sources": sources,
        "limits": config.limits.model_dump(mode="json"),
        "providers": providers,
        "editor_argv": list(config.editor_argv),
        "ui": config.ui.model_dump(mode="json"),
    }
    redacted = redactor.redact(payload)
    assert isinstance(redacted, dict)
    return redacted


def shortcut_list() -> tuple[dict[str, str], ...]:
    return (
        {"keys": "Enter", "action": "提交"},
        {"keys": "Alt+Enter", "action": "插入换行"},
        {"keys": "Up / Down", "action": "浏览历史"},
        {"keys": "Ctrl+R", "action": "历史搜索"},
        {"keys": "Ctrl+G", "action": "外部编辑器"},
        {"keys": "Ctrl+U", "action": "清空输入或撤销排队"},
        {"keys": "Ctrl+C", "action": "取消任务或清空"},
        {"keys": "Ctrl+D", "action": "空闲时退出"},
        {"keys": "End", "action": "回到时间线底部"},
        {"keys": "Cmd+C / Ctrl+Shift+C", "action": "复制选中或最近一块文本"},
    )

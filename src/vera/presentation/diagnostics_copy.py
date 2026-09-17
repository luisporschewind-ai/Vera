"""Human copy for /doctor and /config. Never render secrets."""

from __future__ import annotations

from collections.abc import Mapping


def _kv_lines(mapping: Mapping[str, object]) -> list[str]:
    return [f"{key}  {value}" for key, value in mapping.items()]


def format_doctor_body(payload: Mapping[str, object]) -> str:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return "没有诊断项。"
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        status = str(item.get("status") or "")
        detail = str(item.get("detail") or "")
        if not name:
            continue
        parts = [name]
        if status:
            parts.append(status)
        if detail:
            parts.append(detail)
        lines.append("  ".join(parts))
    return "\n".join(lines) if lines else "没有诊断项。"


def format_config_body(payload: Mapping[str, object]) -> str:
    lines: list[str] = ["来源"]
    sources = payload.get("sources")
    if isinstance(sources, dict) and sources:
        lines.extend(_kv_lines(sources))
    else:
        lines.append("无")

    lines.extend(("", "供应商"))
    providers = payload.get("providers")
    if isinstance(providers, dict) and providers:
        for name, provider in providers.items():
            if not isinstance(provider, dict):
                lines.append(str(name))
                continue
            parts = [str(name)]
            for key in ("model", "base_url", "api_key_env"):
                value = provider.get(key)
                if value:
                    parts.append(str(value))
            lines.append("  ".join(parts))
    else:
        lines.append("无")

    lines.extend(("", "限制"))
    limits = payload.get("limits")
    if isinstance(limits, dict) and limits:
        lines.extend(_kv_lines(limits))
    else:
        lines.append("无")

    editor_argv = payload.get("editor_argv")
    lines.extend(("", "编辑器"))
    if isinstance(editor_argv, list) and editor_argv:
        lines.append(" ".join(str(part) for part in editor_argv))
    else:
        lines.append("无")

    ui = payload.get("ui")
    if isinstance(ui, dict) and ui:
        lines.extend(("", "界面"))
        lines.extend(_kv_lines(ui))
    return "\n".join(lines)

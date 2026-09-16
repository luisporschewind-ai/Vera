#!/usr/bin/env python3
"""Generate Phase 7 CLI visual review SVGs and ASCII fallbacks. Not product code."""

from __future__ import annotations

import html
import unicodedata
from pathlib import Path

OUT = Path(__file__).resolve().parent
CW = 9.0
CH = 22.0
PAD = 14.0
TITLE_H = 26.0
FONT_SIZE = 15.0
BASELINE = 16.0

DEEP = {
    "page": "#07141C",
    "page_text": "#D7E4EE",
    "page_muted": "#7E96A8",
    "bg": "#0B1C28",
    "surface": "#122433",
    "elevated": "#1A3144",
    "text": "#D7E4EE",
    "muted": "#7E96A8",
    "accent": "#3D7A8C",
    "success": "#4A8B6F",
    "warning": "#B08A4A",
    "danger": "#A85A5A",
    "focus": "#5B9BB0",
    "diff_add": "#7EB89A",
    "diff_remove": "#D98989",
    "user": "#D7E4EE",
    "chrome": "#1A3144",
    "border": "#2A4558",
    "btn": "#1A3144",
    "btn_focus": "#3D7A8C",
}
HC = {
    **DEEP,
    "bg": "#000000",
    "surface": "#000000",
    "elevated": "#000000",
    "text": "#FFFFFF",
    "muted": "#FFFFFF",
    "accent": "#FFFF00",
    "success": "#00FF00",
    "warning": "#FFFF00",
    "danger": "#FF4444",
    "focus": "#FFFF00",
    "diff_add": "#00FF00",
    "diff_remove": "#FF4444",
    "user": "#FFFFFF",
    "chrome": "#000000",
    "border": "#FFFFFF",
    "btn": "#000000",
    "btn_focus": "#FFFF00",
}
NC = {
    **DEEP,
    "bg": "#1A1A1A",
    "surface": "#2A2A2A",
    "elevated": "#222222",
    "text": "#E0E0E0",
    "muted": "#B0B0B0",
    "accent": "#B0B0B0",
    "success": "#C8C8C8",
    "warning": "#D0D0D0",
    "danger": "#E0E0E0",
    "focus": "#F0F0F0",
    "diff_add": "#E0E0E0",
    "diff_remove": "#E0E0E0",
    "user": "#E0E0E0",
    "chrome": "#222222",
    "border": "#666666",
    "btn": "#2A2A2A",
    "btn_focus": "#4A4A4A",
}


def dw(ch: str) -> int:
    if ch in "\n\r":
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in {"F", "W"}:
        return 2
    return 1


def width_of(s: str) -> int:
    return sum(dw(c) for c in s)


def clip(s: str, cols: int) -> str:
    out: list[str] = []
    w = 0
    for ch in s:
        cw = dw(ch)
        if w + cw > cols:
            break
        out.append(ch)
        w += cw
    return "".join(out) + " " * (cols - w)


def fit_left_right(left: str, right: str, cols: int, gap: str = "  ") -> str:
    rw = width_of(right)
    lw_max = cols - rw - width_of(gap)
    if lw_max < 0:
        return clip(right, cols)
    left_c = clip(left, lw_max).rstrip()
    pad = cols - width_of(left_c) - rw
    if pad < 1:
        pad = 1
        left_c = clip(left, cols - rw - 1).rstrip()
        pad = cols - width_of(left_c) - rw
    return left_c + (" " * pad) + right


class Seg(list):
    """Colored segments: list of (text, color_key)."""


def S(*parts: str | tuple[str, str]) -> Seg:
    segs = Seg()
    for p in parts:
        if isinstance(p, tuple):
            segs.append(p)
        else:
            segs.append((p, "text"))
    return segs


def segs_text(segs: Seg) -> str:
    return "".join(t for t, _ in segs)


def pad_segs(segs: Seg, cols: int) -> Seg:
    raw = segs_text(segs)
    w = width_of(raw)
    if w < cols:
        return Seg(list(segs) + [(" " * (cols - w), "text")])
    if w == cols:
        return segs
    out = Seg()
    used = 0
    for text, color in segs:
        for ch in text:
            cw = dw(ch)
            if used + cw > cols:
                return out
            out.append((ch, color))
            used += cw
    if used < cols:
        out.append((" " * (cols - used), "text"))
    return out


def bar(pct: int, cells: int) -> str:
    filled = round(pct / 100 * cells)
    return "█" * filled + "░" * (cells - filled)


def header_id(scheme: str, cols: int, *, compact: bool, glyph: bool = False) -> str:
    if scheme == "a":
        return "VERA" if compact else " VERA"
    mark = "   " if glyph else "[V]"
    if scheme == "b":
        return mark if compact else f" {mark}"
    if compact:
        return mark
    return f" {mark} VERA"


def header_line(
    scheme: str,
    cols: int,
    *,
    workspace: str,
    git: str,
    session: str,
    clock: str = "10:24",
    compact: bool = False,
    glyph: bool = False,
) -> Seg:
    ident = header_id(scheme, cols, compact=compact, glyph=glyph)
    mid_bits = [workspace]
    if git:
        mid_bits.append(git)
    if session:
        mid_bits.append(session)
    mid = "  ".join(mid_bits)
    rest_cols = cols - width_of(ident)
    if rest_cols <= 0:
        return S((clip(ident, cols), "accent"))
    if compact:
        rest = clip("  " + mid, rest_cols)
        return S((ident, "accent"), (rest, "muted"))
    inner = rest_cols - width_of(clock)
    if inner < 2:
        return S((ident, "accent"), (clip(clock, rest_cols), "muted"))
    mid_c = clip("  " + mid, inner).rstrip()
    pad = rest_cols - width_of(mid_c) - width_of(clock)
    if pad < 1:
        mid_c = clip("  " + mid, inner - 1).rstrip()
        pad = rest_cols - width_of(mid_c) - width_of(clock)
    return S((ident, "accent"), (mid_c + (" " * pad), "muted"), (clock, "muted"))


def brand_header(
    scheme: str,
    cols: int,
    *,
    workspace: str,
    git: str,
    session: str,
    two_line: bool,
    glyph: bool = False,
) -> list[Seg]:
    ident = header_id(scheme, cols, compact=cols <= 60, glyph=glyph)
    if two_line:
        top = fit_left_right(ident, "", cols)
        second = fit_left_right(f" {workspace}  {git}  {session}".rstrip(), "10:24", cols)
        return [S((clip(top, cols), "accent")), S((second, "muted"))]
    return [
        header_line(
            scheme,
            cols,
            workspace=workspace,
            git=git,
            session=session,
            compact=cols <= 60,
            glyph=glyph,
        )
    ]


def sticky_user(cols: int, text: str = "把背景改成深海绿", clock: str = "10:24") -> Seg:
    line = fit_left_right(f" {text}", clock, cols)
    return S((line, "user"))


def composer(cols: int, prompt: str = "▸ ") -> list[Seg]:
    rule = "─" * cols
    return [S((rule, "border")), S((clip(f" {prompt}_", cols), "accent"))]


def status_band(
    cols: int,
    *,
    keep: str = "both",
    pct: int = 24,
    model: str = "deepseek-chat",
    reasoning: str = "推理 模型默认",
) -> Seg:
    left = f" 会话上下文 {bar(pct, 8)} {pct}%"
    if cols <= 60:
        if keep == "model":
            line = fit_left_right(f" {model}", reasoning, cols)
        elif keep == "context":
            line = fit_left_right(f" 上下文 {bar(pct, 6)} {pct}%", reasoning, cols)
        else:
            line = fit_left_right(f" 上下文 {pct}%", model, cols)
        return S((line, "muted"))
    right = f"{model}  {reasoning}"
    if keep == "context":
        right = reasoning
    elif keep == "model":
        left = f" {model}"
    line = fit_left_right(left, right, cols)
    return S((line, "muted"))


def buttons(cols: int) -> Seg:
    label = " [ 取消 ]  [ 拒绝 ]  [ 批准 ]"
    if cols <= 60:
        label = " [取消] [拒绝] [批准]"
    return S(
        (" [ 取消 ]", "muted") if cols > 60 else (" [取消]", "muted"),
        ("  [ 拒绝 ]", "danger") if cols > 60 else (" [拒绝]", "danger"),
        ("  [ 批准 ]", "focus") if cols > 60 else (" [批准]", "focus"),
        (" " * max(0, cols - width_of(label)), "text"),
    )


def diff_lines(cols: int, *, compact: bool) -> list[Seg]:
    title = " Diff · ViewController.swift（update）"
    if cols <= 60:
        title = " Diff · ViewController.swift"
    minus = " - view.backgroundColor = .blue"
    plus = " + view.backgroundColor = .green"
    if compact and cols <= 60:
        minus = " - backgroundColor = .blue"
        plus = " + backgroundColor = .green"
    lines = [S((clip(title, cols), "muted"))]
    if not compact and cols >= 120:
        lines.append(S((clip("   1  file  update", cols), "muted")))
    lines.append(S((clip(minus, cols), "diff_remove")))
    lines.append(S((clip(plus, cols), "diff_add")))
    return lines


def approval_block(cols: int) -> list[Seg]:
    if cols <= 60:
        return [
            S((clip(" 待批准 · 风险 medium", cols), "warning")),
            S((clip(" 写入 1 个文件。", cols), "muted")),
            buttons(cols),
        ]
    return [
        S((clip(" 待批准 Change Set · 风险 medium", cols), "warning")),
        S((clip(" 写入 1 个文件。无验证命令。", cols), "muted")),
        buttons(cols),
    ]


def tool_block(cols: int, *, expanded: bool) -> list[Seg]:
    if expanded and cols >= 80:
        return [
            S((clip(" 读取  ViewController.swift", cols), "text")),
            S((clip("   完成 · 41ms · 41 行", cols), "success")),
        ]
    return [S((clip(" 读取  ViewController.swift  · 完成 · 41ms", cols), "success"))]


def blank(cols: int) -> Seg:
    return S((" " * cols, "text"))


def screen_60(
    scheme: str, *, session: str = "新会话", keep: str = "context", glyph: bool = False
) -> list[Seg]:
    cols = 60
    lines: list[Seg] = []
    lines.extend(
        brand_header(
            scheme,
            cols,
            workspace="VeraTestDemo",
            git="dirty",
            session=session,
            two_line=False,
            glyph=glyph,
        )
    )
    lines.append(sticky_user(cols))
    lines.append(blank(cols))
    lines.append(S((clip(" 将修改 ViewController.swift", cols), "text")))
    lines.append(S((clip(" 的背景色。", cols), "text")))
    lines.extend(tool_block(cols, expanded=False))
    lines.extend(diff_lines(cols, compact=True))
    lines.extend(approval_block(cols))
    lines.extend(composer(cols))
    lines.append(status_band(cols, keep=keep))
    while len(lines) < 16:
        lines.insert(len(lines) - 3, blank(cols))
    return lines[:16]


def screen_80(
    scheme: str,
    *,
    two_line: bool = False,
    expanded_tool: bool = False,
    session: str = "已恢复",
    git: str = "main*",
    workspace: str = "VeraTestDemo",
    glyph: bool = False,
) -> list[Seg]:
    cols = 80
    lines: list[Seg] = []
    lines.extend(
        brand_header(
            scheme,
            cols,
            workspace=workspace,
            git=git,
            session=session,
            two_line=two_line,
            glyph=glyph,
        )
    )
    lines.append(sticky_user(cols))
    lines.append(blank(cols))
    lines.append(S((clip(" 将修改 ViewController.swift 的背景色。", cols), "text")))
    lines.append(S((clip(" 启动页会更接近深海，而不是默认蓝。", cols), "text")))
    lines.append(blank(cols))
    lines.extend(tool_block(cols, expanded=expanded_tool))
    lines.append(blank(cols))
    lines.extend(diff_lines(cols, compact=False))
    lines.append(blank(cols))
    lines.extend(approval_block(cols))
    lines.append(S((clip(" 验证  未排队", cols), "muted")))
    lines.extend(composer(cols))
    lines.append(status_band(cols, keep="both"))
    while len(lines) < 24:
        lines.insert(len(lines) - 3, blank(cols))
    return lines[:24]


def screen_80_cards(scheme: str, *, glyph: bool = False) -> list[Seg]:
    """Task-card axis: no sticky user; approval card is the visual center."""
    cols = 80
    lines: list[Seg] = []
    lines.extend(
        brand_header(
            scheme,
            cols,
            workspace="VeraTestDemo",
            git="main*",
            session="已恢复",
            two_line=False,
            glyph=glyph,
        )
    )
    lines.append(S((clip(" 把背景改成深海绿                              10:24", cols), "user")))
    lines.append(S((clip(" 将修改 ViewController.swift 的背景色。", cols), "text")))
    lines.extend(tool_block(cols, expanded=False))
    lines.append(blank(cols))
    lines.append(S((clip(" ┌ Diff / 审批卡 ─────────────────────────────────┐", cols), "warning")))
    lines.extend(diff_lines(cols, compact=False))
    lines.extend(approval_block(cols))
    lines.append(S((clip(" └────────────────────────────────────────────────┘", cols), "warning")))
    lines.append(S((clip(" 备选主轴：卡片最重，用户消息不钉顶。", cols), "muted")))
    lines.extend(composer(cols))
    lines.append(status_band(cols, keep="both"))
    while len(lines) < 24:
        lines.insert(len(lines) - 3, blank(cols))
    return lines[:24]


def screen_80_anchor(scheme: str, frame: int, *, glyph: bool = False) -> list[Seg]:
    cols = 80
    lines: list[Seg] = []
    lines.extend(
        brand_header(
            scheme,
            cols,
            workspace="VeraTestDemo",
            git="main*",
            session="已恢复",
            two_line=False,
            glyph=glyph,
        )
    )
    if frame == 1:
        lines.append(S((clip(" 上一轮助手：已列出可选背景色。", cols), "muted")))
        lines.append(blank(cols))
        lines.append(S((clip(" 把背景改成深海绿                              10:24", cols), "user")))
        lines.append(blank(cols))
        lines.append(S((clip(" 将修改 ViewController.swift 的背景色。", cols), "text")))
        lines.extend(tool_block(cols, expanded=False))
        lines.extend(diff_lines(cols, compact=False))
        lines.append(S((clip(" 时间线中的用户消息，尚未钉到顶部。", cols), "muted")))
    else:
        lines.append(sticky_user(cols))
        lines.append(S((clip(" 将修改 ViewController.swift 的背景色。", cols), "text")))
        lines.extend(tool_block(cols, expanded=False))
        lines.extend(diff_lines(cols, compact=False))
        lines.extend(approval_block(cols))
        lines.append(blank(cols))
        lines.append(S((clip(" 再把标题字号加大                              10:31", cols), "user")))
        lines.append(S((clip(" 上一条用户消息已成为顶部锚点；本条仍在时间线。", cols), "muted")))
    lines.extend(composer(cols))
    lines.append(status_band(cols, keep="both"))
    while len(lines) < 24:
        lines.insert(len(lines) - 3, blank(cols))
    return lines[:24]


def screen_120(scheme: str, *, glyph: bool = False) -> list[Seg]:
    cols = 120
    lines: list[Seg] = []
    lines.extend(
        brand_header(
            scheme,
            cols,
            workspace="/Users/admin/VeraTestDemo",
            git="main*",
            session="已恢复",
            two_line=False,
            glyph=glyph,
        )
    )
    lines.append(sticky_user(cols))
    lines.append(blank(cols))
    lines.append(S((clip(" 将修改 ViewController.swift 的背景色，使启动页更接近深海。", cols), "text")))
    lines.append(blank(cols))
    lines.extend(tool_block(cols, expanded=True))
    lines.append(blank(cols))
    lines.extend(diff_lines(cols, compact=False))
    lines.append(blank(cols))
    lines.extend(approval_block(cols))
    lines.append(blank(cols))
    lines.append(S((clip(" 验证  未排队（本 Change Set 无验证命令）", cols), "muted")))
    lines.append(blank(cols))
    lines.append(S((clip(" ── 非 Git / 新会话对照 ──", cols), "muted")))
    ident = header_id(scheme, cols, compact=False, glyph=glyph)
    lines.append(S((ident, "accent"), (clip(f"  /tmp/plain-project  非 Git  新会话                10:02", cols - width_of(ident)), "muted")))
    lines.append(blank(cols))
    lines.append(S((clip(" ── 状态对照 ──", cols), "muted")))
    lines.append(S((clip(" idle        等待输入", cols), "muted")))
    lines.append(S((clip(" running     运行中 · 读取 ViewController.swift", cols), "accent")))
    lines.append(S((clip(" completed   本轮完成", cols), "success")))
    lines.append(S((clip(" failed      写入失败 · EACCES  Permission denied", cols), "danger")))
    lines.extend(composer(cols))
    lines.append(status_band(cols, keep="both", pct=12))
    while len(lines) < 40:
        lines.insert(len(lines) - 3, blank(cols))
    return lines[:40]


def asciiize(s: str) -> str:
    table = str.maketrans(
        {
            "─": "-",
            "░": ".",
            "█": "#",
            "▸": ">",
            "·": "*",
            "┌": "+",
            "┐": "+",
            "└": "+",
            "┘": "+",
            "│": "|",
        }
    )
    s = s.translate(table)
    s = s.replace("[V]", "[V]")
    s = s.replace("（", "(").replace("）", ")")
    return s


def segs_to_ascii(segs: Seg) -> str:
    return asciiize(segs_text(segs).rstrip())


def frame_to_txt(title: str, lines: list[Seg], cols: int) -> str:
    border = "+" + ("-" * cols) + "+"
    body = "\n".join("|" + clip(segs_text(line), cols) + "|" for line in lines)
    return f"{title}\n{border}\n{body}\n{border}\n"


def vstar_svg(x: float, y: float, size: float, pal: dict[str, str]) -> str:
    s = size
    star = (
        f"M{x + s * 0.50:.1f},{y + s * 0.02:.1f} "
        f"L{x + s * 0.58:.1f},{y + s * 0.28:.1f} "
        f"L{x + s * 0.86:.1f},{y + s * 0.30:.1f} "
        f"L{x + s * 0.64:.1f},{y + s * 0.48:.1f} "
        f"L{x + s * 0.72:.1f},{y + s * 0.76:.1f} "
        f"L{x + s * 0.50:.1f},{y + s * 0.60:.1f} "
        f"L{x + s * 0.28:.1f},{y + s * 0.76:.1f} "
        f"L{x + s * 0.36:.1f},{y + s * 0.48:.1f} "
        f"L{x + s * 0.14:.1f},{y + s * 0.30:.1f} "
        f"L{x + s * 0.42:.1f},{y + s * 0.28:.1f} Z"
    )
    v = (
        f"M{x + s * 0.18:.1f},{y + s * 0.22:.1f} "
        f"L{x + s * 0.50:.1f},{y + s * 0.92:.1f} "
        f"L{x + s * 0.82:.1f},{y + s * 0.22:.1f}"
    )
    return (
        f'<path d="{v}" fill="none" stroke="{pal["focus"]}" '
        f'stroke-width="{max(1.6, s / 10):.1f}" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
        f'<path d="{star}" fill="{pal["warning"]}" stroke="{pal["warning"]}" stroke-width="0.4"/>'
    )


def wordmark_svg(x: float, y: float, size: float, pal: dict[str, str]) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{pal["focus"]}" '
        f'font-family="Avenir Next, Helvetica Neue, SF Pro Display, sans-serif" '
        f'font-size="{size:.0f}" font-weight="600" letter-spacing="0.22em">VERA</text>'
    )


def identity_hero(scheme: str, x: float, y: float, pal: dict[str, str]) -> str:
    parts = [f'<g id="hero-{scheme}">']
    if scheme == "a":
        parts.append(wordmark_svg(x, y + 36, 36, pal))
        parts.append(
            f'<text x="{x:.1f}" y="{y + 64:.1f}" fill="{pal["page_muted"]}" font-size="13" '
            f'font-family="Menlo, monospace">完整字标 · 紧凑退化为文字 VERA</text>'
        )
    elif scheme == "b":
        parts.append(vstar_svg(x, y, 48, pal))
        parts.append(
            f'<text x="{x + 64:.1f}" y="{y + 32:.1f}" fill="{pal["focus"]}" font-size="22" '
            f'font-family="Menlo, monospace">[V]</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y + 72:.1f}" fill="{pal["page_muted"]}" font-size="13" '
            f'font-family="Menlo, monospace">V 星点母形 · ASCII 为 [V]</text>'
        )
    else:
        parts.append(vstar_svg(x, y, 48, pal))
        parts.append(wordmark_svg(x + 64, y + 36, 32, pal))
        parts.append(
            f'<text x="{x:.1f}" y="{y + 72:.1f}" fill="{pal["page_muted"]}" font-size="13" '
            f'font-family="Menlo, monospace">组合标识 · 60 列只保留母形 / [V]</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def draw_line_svg(x: float, y: float, segs: Seg, pal: dict[str, str], cols: int) -> str:
    """ASCII stays on the Menlo grid; CJK is placed in two cells. No whole-line stretching."""
    parts: list[str] = []
    col = 0
    for text, key in pad_segs(segs, cols):
        fill = pal.get(key, pal["text"])
        i = 0
        while i < len(text) and col < cols:
            ch = text[i]
            w = dw(ch)
            if w == 2:
                if ch != " ":
                    cx = x + col * CW
                    parts.append(
                        f'<text x="{cx:.1f}" y="{y:.1f}" textLength="{2 * CW:.1f}" '
                        f'lengthAdjust="spacingAndGlyphs" xml:space="preserve" fill="{fill}">'
                        f"{html.escape(ch)}</text>"
                    )
                col += 2
                i += 1
                continue
            start = col
            chunk: list[str] = []
            while i < len(text) and dw(text[i]) == 1 and col < cols:
                chunk.append(text[i])
                col += 1
                i += 1
            rendered = "".join(chunk)
            if rendered.strip(" "):
                cx = x + start * CW
                parts.append(
                    f'<text x="{cx:.1f}" y="{y:.1f}" xml:space="preserve" fill="{fill}">'
                    f"{html.escape(rendered)}</text>"
                )
    return "".join(parts)


def terminal_svg(
    x: float,
    y: float,
    cols: int,
    rows: int,
    lines: list[Seg],
    pal: dict[str, str],
    caption: str,
    *,
    sticky_rows: tuple[int, ...] = (),
    composer_rows: tuple[int, ...] | None = None,
    scheme: str = "a",
    show_mark: bool = True,
) -> tuple[str, float, float]:
    tw = cols * CW + PAD * 2
    th = TITLE_H + rows * CH + PAD
    if composer_rows is None:
        composer_rows = (rows - 3, rows - 2)
    bits: list[str] = []
    bits.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{tw:.1f}" height="{th:.1f}" '
        f'rx="8" fill="{pal["bg"]}" stroke="{pal["border"]}" stroke-width="1.2"/>'
    )
    bits.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{tw:.1f}" height="{TITLE_H:.1f}" '
        f'rx="8" fill="{pal["chrome"]}"/>'
    )
    bits.append(
        f'<rect x="{x:.1f}" y="{y + 12:.1f}" width="{tw:.1f}" height="{TITLE_H - 12:.1f}" fill="{pal["chrome"]}"/>'
    )
    for i, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        bits.append(
            f'<circle cx="{x + 14 + i * 12:.1f}" cy="{y + 11:.1f}" r="3.2" fill="{color}"/>'
        )
    bits.append(
        f'<text x="{x + tw / 2:.1f}" y="{y + 16:.1f}" text-anchor="middle" fill="{pal["muted"]}" '
        f'font-size="11" font-family="Menlo, monospace">{html.escape(caption)}</text>'
    )
    origin_x = x + PAD
    origin_y = y + TITLE_H + 4
    clip_id = f"term-{int(x)}-{int(y)}-{cols}x{rows}"
    bits.append(
        f'<defs><clipPath id="{clip_id}">'
        f'<rect x="{origin_x:.1f}" y="{origin_y:.1f}" width="{cols * CW:.1f}" height="{rows * CH:.1f}"/>'
        f"</clipPath></defs>"
    )
    for idx in sticky_rows:
        bits.append(
            f'<rect x="{origin_x:.1f}" y="{origin_y + idx * CH:.1f}" width="{cols * CW:.1f}" '
            f'height="{CH:.1f}" fill="{pal["elevated"]}"/>'
        )
    if composer_rows:
        cr0, cr1 = composer_rows
        bits.append(
            f'<rect x="{origin_x + 1:.1f}" y="{origin_y + cr0 * CH + 1:.1f}" '
            f'width="{cols * CW - 2:.1f}" height="{CH * (cr1 - cr0 + 1) - 2:.1f}" '
            f'fill="none" stroke="{pal["accent"]}" stroke-width="1" rx="3"/>'
        )
    bits.append(
        f'<g clip-path="url(#{clip_id})" font-family="Menlo, PingFang SC, Hiragino Sans GB, monospace" '
        f'font-size="{FONT_SIZE:.0f}" xml:space="preserve">'
    )
    for i, line in enumerate(lines[:rows]):
        ty = origin_y + i * CH + BASELINE
        bits.append(draw_line_svg(origin_x, ty, line, pal, cols))
    bits.append("</g>")
    if show_mark and scheme in {"b", "c"}:
        bits.append(vstar_svg(origin_x + 1, y + TITLE_H + 1, 14, pal))
    return "".join(bits), tw, th


def caption_svg(x: float, y: float, text: str, pal: dict[str, str]) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{pal["page_muted"]}" font-size="13" '
        f'font-family="PingFang SC, Helvetica Neue, sans-serif">{html.escape(text)}</text>'
    )


def token_strip(x: float, y: float, pal: dict[str, str]) -> str:
    keys = [
        ("bg", "background"),
        ("surface", "surface"),
        ("elevated", "surface_elevated"),
        ("text", "text_primary"),
        ("muted", "text_muted"),
        ("accent", "accent"),
        ("success", "success"),
        ("warning", "warning"),
        ("danger", "danger"),
        ("focus", "focus"),
        ("diff_add", "diff_add"),
        ("diff_remove", "diff_remove"),
    ]
    bits = [caption_svg(x, y - 12, "拟议深海 Token（未冻结，选择前不写入规格）", pal)]
    for i, (key, name) in enumerate(keys):
        cx = x + (i % 3) * 360
        cy = y + (i // 3) * 36
        bits.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="18" height="18" rx="3" fill="{pal[key]}" stroke="#2A4558"/>')
        bits.append(
            f'<text x="{cx + 26:.1f}" y="{cy + 14:.1f}" fill="{pal["page_text"]}" font-size="11" '
            f'font-family="Menlo, monospace">{name}  {pal[key]}</text>'
        )
    return "".join(bits)


def build_svg(scheme: str, title: str, subtitle: str) -> str:
    pal = DEEP
    width = 1200
    g = True
    parts: list[str] = []
    y = 36
    parts.append(
        f'<text x="40" y="{y}" fill="{pal["page_text"]}" font-size="26" font-weight="600" '
        f'font-family="PingFang SC, Helvetica Neue, sans-serif">{html.escape(title)}</text>'
    )
    y += 28
    parts.append(caption_svg(40, y, subtitle, pal))
    y += 24
    parts.append(identity_hero(scheme, 40, y, pal))
    y += 100
    parts.append(token_strip(40, y, pal))
    y += 180

    def add_term(lines, cols, rows, caption, sticky=(), cx=40, show_mark=True, palette=None):
        p = palette or pal
        svg, tw, th = terminal_svg(
            cx, y, cols, rows, lines, p, caption, sticky_rows=sticky, scheme=scheme, show_mark=show_mark
        )
        parts.append(svg)
        return tw, th

    parts.append(caption_svg(40, y, "60×16 主提案：状态带保留上下文百分比（模型名让出）", pal))
    y += 18
    tw, th = add_term(
        screen_60(scheme, session="新会话", keep="context", glyph=g),
        60,
        16,
        "60×16 新会话 · Git dirty",
        sticky=(1,),
    )
    y += th + 32
    parts.append(caption_svg(40, y, "60×16 备选：状态带保留模型名（百分比让出）", pal))
    y += 18
    tw, th = add_term(
        screen_60(scheme, session="新会话", keep="model", glyph=g),
        60,
        16,
        "60×16 备选状态带",
        sticky=(1,),
    )
    y += th + 36

    parts.append(
        caption_svg(
            40,
            y,
            "80×24 主流程：一行品牌 · 工具一行披露 · 已恢复 · 审批三行连续，卡内无空洞。卡下空白是时间线剩余高度。",
            pal,
        )
    )
    y += 18
    tw, th = add_term(screen_80(scheme, two_line=False, glyph=g), 80, 24, "80×24 审批 · 已恢复 · main*", sticky=(1,))
    y += th + 28
    parts.append(caption_svg(40, y, "80×24 备选品牌高度：两行品牌区（标识独占第一行）", pal))
    y += 18
    tw, th = add_term(screen_80(scheme, two_line=True, glyph=g), 80, 24, "80×24 两行品牌备选", sticky=(2,))
    y += th + 28
    parts.append(caption_svg(40, y, "80×24 备选工具密度：工具展开为两行（标题 + 完成/耗时/行数）", pal))
    y += 18
    tw, th = add_term(
        screen_80(scheme, two_line=False, expanded_tool=True, glyph=g),
        80,
        24,
        "80×24 工具展开备选",
        sticky=(1,),
    )
    y += th + 36

    parts.append(
        caption_svg(
            40,
            y,
            "用户消息锚点两帧（对话主轴）：先看时间线内的用户消息，下一帧钉到顶部",
            pal,
        )
    )
    y += 18
    tw, th = add_term(
        screen_80_anchor(scheme, 1, glyph=g),
        80,
        24,
        "锚点帧 1 · 时间线内",
        sticky=(),
    )
    y += th + 28
    parts.append(caption_svg(40, y, "锚点帧 2：上一条用户消息钉到顶部，下一条出现在时间线", pal))
    y += 18
    tw, th = add_term(
        screen_80_anchor(scheme, 2, glyph=g),
        80,
        24,
        "锚点帧 2 · 顶部锚点 + 新用户消息",
        sticky=(1,),
    )
    parts.append(caption_svg(40, y, "备选时间线主轴：任务卡片（用户不钉顶，Diff/审批卡最重）", pal))
    y += 18
    tw, th = add_term(screen_80_cards(scheme, glyph=g), 80, 24, "80×24 任务卡片主轴", sticky=())
    y += th + 36

    parts.append(
        caption_svg(
            40,
            y,
            "120×40：展开工具披露、完整路径、非 Git/新会话对照、idle/running/completed/failed；上下文 12%",
            pal,
        )
    )
    y += 18
    tw, th = add_term(screen_120(scheme, glyph=g), 120, 40, "120×40 Git dirty · 已恢复", sticky=(1,))
    y += th + 36

    parts.append(caption_svg(40, y, "回退：ASCII（无盒线/无 Emoji/无 Nerd Font）· 高对比 · NO_COLOR", pal))
    y += 18
    tw, th = add_term(
        [S((clip(asciiize(segs_text(s)), 80), "text")) for s in screen_80(scheme)],
        80,
        24,
        "ASCII 80×24",
        sticky=(1,),
        show_mark=False,
    )
    y += th + 28
    parts.append(caption_svg(40, y, "high-contrast 80×24", pal))
    y += 18
    tw, th = add_term(screen_80(scheme, glyph=g), 80, 24, "high-contrast 80×24", sticky=(1,), palette=HC)
    y += th + 28
    parts.append(caption_svg(40, y, "NO_COLOR 80×24", pal))
    y += 18
    tw, th = add_term(screen_80(scheme, glyph=g), 80, 24, "NO_COLOR 80×24", sticky=(1,), palette=NC)
    y += th + 48
    parts.append(
        caption_svg(
            40,
            y,
            "共同假数据：workspace /Users/admin/VeraTestDemo · 用户「把背景改成深海绿」10:24 · 模型 deepseek-chat · 推理「模型默认」· 批准/拒绝/取消。不含第三方商标。",
            pal,
        )
    )
    y += 32
    height = y + 20
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height:.0f}" '
        f'viewBox="0 0 {width} {height:.0f}" role="img">'
        f'<rect width="100%" height="100%" fill="{pal["page"]}"/>'
        + "".join(parts)
        + "</svg>\n"
    )


def build_txt(scheme: str, title: str) -> str:
    chunks = [
        title,
        "纯文本回退。不依赖 Nerd Font、Emoji 宽度或真彩色。请在 Terminal.app 默认字体（Menlo）中打开本文件对照 CJK/宽字符。",
        "共同假数据：/Users/admin/VeraTestDemo · 把背景改成深海绿 · ViewController.swift · deepseek-chat · 推理 模型默认",
        "",
        frame_to_txt("60x16 新会话 · 状态带保留上下文百分比", screen_60(scheme, keep="context"), 60),
        frame_to_txt("60x16 备选 · 状态带保留模型名", screen_60(scheme, keep="model"), 60),
        frame_to_txt("80x24 一行品牌 · 已恢复 · 审批", screen_80(scheme, two_line=False), 80),
        frame_to_txt("80x24 两行品牌备选", screen_80(scheme, two_line=True), 80),
        frame_to_txt("80x24 工具展开备选", screen_80(scheme, expanded_tool=True), 80),
        frame_to_txt("80x24 锚点帧 1 用户仍在时间线", screen_80_anchor(scheme, 1), 80),
        frame_to_txt("80x24 锚点帧 2 顶部锚点 + 下一条用户消息", screen_80_anchor(scheme, 2), 80),
        frame_to_txt("80x24 备选任务卡片主轴", screen_80_cards(scheme), 80),
        frame_to_txt("120x40 展开披露 · 非 Git 对照 · 多状态", screen_120(scheme), 120),
        frame_to_txt(
            "ASCII 80x24",
            [S((clip(asciiize(segs_text(s)), 80), "text")) for s in screen_80(scheme)],
            80,
        ),
    ]
    return "\n".join(chunks) + "\n"


def main() -> None:
    specs = [
        ("a", "方案 A · 完整字标", "识别度靠 VERA 四字。窄屏仍是文字，不引入图形母形。桌面延展直接用字标。"),
        ("b", "方案 B · V 星点母形", "识别度靠几何 V + 星点；ASCII 为 [V]。占列少，桌面可做独立图标。"),
        ("c", "方案 C · 组合标识", "宽屏母形+字标，60 列只留母形/[V]。实现与阈值更复杂，延展最完整。"),
    ]
    names = {
        "a": "phase-7-cli-visual-a-wordmark",
        "b": "phase-7-cli-visual-b-v-star",
        "c": "phase-7-cli-visual-c-combination",
    }
    errors: list[str] = []
    for scheme, title, subtitle in specs:
        frames = [
            (60, screen_60(scheme)),
            (80, screen_80(scheme)),
            (80, screen_80(scheme, two_line=True)),
            (120, screen_120(scheme)),
        ]
        for cols, lines in frames:
            if len(lines) != {60: 16, 80: 24, 120: 40}[cols]:
                errors.append(f"{scheme} {cols} rows={len(lines)}")
            for i, line in enumerate(lines):
                w = width_of(segs_text(pad_segs(line, cols)))
                if w != cols:
                    errors.append(f"{scheme} {cols}c line {i} width={w}")
        svg = build_svg(scheme, title, subtitle)
        txt = build_txt(scheme, title)
        xmlns_ok = 'xmlns="http://www.w3.org/2000/svg"' in svg
        stripped = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
        if "http://" in stripped or "https://" in stripped:
            errors.append(f"{scheme} svg has external url")
        if not xmlns_ok:
            errors.append(f"{scheme} svg missing xmlns")
        (OUT / f"{names[scheme]}.svg").write_text(svg, encoding="utf-8")
        (OUT / f"{names[scheme]}.txt").write_text(txt, encoding="utf-8")
        print(f"wrote {names[scheme]} svg={len(svg)} txt={len(txt)}")
    if errors:
        raise SystemExit("layout errors:\n" + "\n".join(errors))


if __name__ == "__main__":
    main()

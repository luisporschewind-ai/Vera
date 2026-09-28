"""Parsers for Git's stable machine-readable output formats."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from vera.git.models import GitStatusEntry


class GitParserError(ValueError):
    """Raised when Git machine output cannot be safely interpreted."""


@dataclass(frozen=True)
class ParsedStatus:
    head_oid: str | None
    branch: str | None
    detached: bool
    unborn: bool
    upstream: str | None
    ahead: int
    behind: int
    entries: tuple[GitStatusEntry, ...]


def parse_status_porcelain_v2(payload: bytes) -> ParsedStatus:
    records = payload.split(b"\0")
    head_oid: str | None = None
    branch: str | None = None
    detached = False
    unborn = False
    upstream: str | None = None
    ahead = 0
    behind = 0
    entries: list[GitStatusEntry] = []
    index = 0
    while index < len(records):
        raw = records[index]
        index += 1
        if not raw:
            continue
        text = os.fsdecode(raw)
        if text.startswith("# "):
            head_oid, branch, detached, unborn, upstream, ahead, behind = _parse_header(
                text,
                head_oid=head_oid,
                branch=branch,
                detached=detached,
                unborn=unborn,
                upstream=upstream,
                ahead=ahead,
                behind=behind,
            )
            continue
        kind = text[0]
        if kind == "?":
            entries.append(GitStatusEntry(path=os.fsdecode(raw[2:] or b""), untracked=True))
            continue
        if kind == "!":
            entries.append(GitStatusEntry(path=os.fsdecode(raw[2:] or b""), ignored=True))
            continue
        if kind == "1":
            entries.append(_ordinary_entry(text))
            continue
        if kind == "2":
            entry, original_consumed = _rename_entry(text, records, index)
            index += original_consumed
            entries.append(entry)
            continue
        if kind == "u":
            entries.append(_unmerged_entry(text))
            continue
        raise GitParserError(f"unsupported porcelain v2 record: {kind!r}")
    return ParsedStatus(
        head_oid=head_oid,
        branch=branch,
        detached=detached,
        unborn=unborn,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        entries=tuple(entries),
    )


def _parse_header(
    text: str,
    *,
    head_oid: str | None,
    branch: str | None,
    detached: bool,
    unborn: bool,
    upstream: str | None,
    ahead: int,
    behind: int,
) -> tuple[str | None, str | None, bool, bool, str | None, int, int]:
    key, _, value = text[2:].partition(" ")
    if key == "branch.oid":
        if value == "(initial)":
            return None, branch, detached, True, upstream, ahead, behind
        return value or None, branch, detached, unborn, upstream, ahead, behind
    if key == "branch.head":
        if value == "(detached)":
            return head_oid, None, True, unborn, upstream, ahead, behind
        return head_oid, value or None, detached, unborn, upstream, ahead, behind
    if key == "branch.upstream":
        return head_oid, branch, detached, unborn, value or None, ahead, behind
    if key == "branch.ab":
        match = re.fullmatch(r"\+([0-9]+) -([0-9]+)", value)
        if match is None:
            raise GitParserError("invalid branch ahead/behind header")
        return head_oid, branch, detached, unborn, upstream, int(match[1]), int(match[2])
    return head_oid, branch, detached, unborn, upstream, ahead, behind


def _ordinary_entry(text: str) -> GitStatusEntry:
    parts = text.split(" ", 8)
    if len(parts) != 9:
        raise GitParserError("invalid ordinary porcelain v2 record")
    _, xy, submodule, *_metadata, path = parts
    return _entry(
        path=path,
        xy=xy,
        submodule=None if submodule == "N..." else submodule,
    )


def _rename_entry(text: str, records: list[bytes], index: int) -> tuple[GitStatusEntry, int]:
    parts = text.split(" ", 9)
    if len(parts) != 10 or index >= len(records) or not records[index]:
        raise GitParserError("invalid rename porcelain v2 record")
    _, xy, submodule, *_metadata, _score, path = parts
    original_path = os.fsdecode(records[index])
    return (
        _entry(
            path=path,
            xy=xy,
            submodule=None if submodule == "N..." else submodule,
            original_path=original_path,
        ),
        1,
    )


def _unmerged_entry(text: str) -> GitStatusEntry:
    parts = text.split(" ", 10)
    if len(parts) != 11:
        raise GitParserError("invalid unmerged porcelain v2 record")
    _, xy, submodule, *_metadata, path = parts
    return _entry(
        path=path,
        xy=xy,
        submodule=None if submodule == "N..." else submodule,
        conflicted=True,
    )


def _entry(
    *,
    path: str,
    xy: str,
    submodule: str | None,
    original_path: str | None = None,
    conflicted: bool = False,
) -> GitStatusEntry:
    if len(xy) != 2:
        raise GitParserError("invalid porcelain v2 status pair")
    return GitStatusEntry(
        path=path,
        original_path=original_path,
        staged=xy[0],
        unstaged=xy[1],
        conflicted=conflicted or "U" in xy,
        submodule=submodule,
    )

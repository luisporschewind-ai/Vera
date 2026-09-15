"""Root CLI session-flag parsing. Returns SessionOpenRequest only."""

from __future__ import annotations

from collections.abc import Sequence

from vera.session.startup import SessionOpenRequest, SessionStartupError

ROOT_SUBCOMMANDS = frozenset(
    {"run", "runs", "eval", "config", "recover", "state", "rollback", "sessions"}
)
_VALUE_OPTIONS = frozenset({"--workspace", "--model"})
_FLAG_OPTIONS = frozenset({"--plain", "--json", "--version", "-V", "--help", "-h"})


def parse_session_open_request(argv: Sequence[str]) -> SessionOpenRequest:
    tokens = list(argv)
    continue_flag = False
    resume_flag = False
    session_id: str | None = None
    command: str | None = None
    extra: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"-c", "--continue"}:
            continue_flag = True
            index += 1
            continue
        if token in {"-r", "--resume"}:
            if resume_flag:
                raise SessionStartupError("duplicate_resume", "重复的 --resume 参数")
            resume_flag = True
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
                session_id = tokens[index + 1]
                index += 2
                continue
            index += 1
            continue
        if token.startswith("--resume="):
            if resume_flag:
                raise SessionStartupError("duplicate_resume", "重复的 --resume 参数")
            resume_flag = True
            session_id = token.split("=", 1)[1] or None
            if not session_id:
                raise SessionStartupError("invalid_session_id", "--resume 需要会话 ID")
            index += 1
            continue
        if token in _VALUE_OPTIONS:
            index += 2
            continue
        if token.startswith("--workspace=") or token.startswith("--model="):
            index += 1
            continue
        if token in _FLAG_OPTIONS or token.startswith("-"):
            index += 1
            continue
        if command is None:
            command = token
            index += 1
            continue
        extra.append(token)
        index += 1

    if command in ROOT_SUBCOMMANDS:
        return SessionOpenRequest(mode="new")
    if command is not None:
        extra = [command, *extra]
        command = None
    if extra:
        raise SessionStartupError("extra_positional", "根命令不接受多余位置参数")
    if continue_flag and resume_flag:
        raise SessionStartupError(
            "continue_resume_conflict",
            "-c/--continue 与 -r/--resume 不能同时使用",
        )
    if continue_flag:
        return SessionOpenRequest(mode="continue")
    if resume_flag and session_id:
        return SessionOpenRequest(mode="resume_id", session_id=session_id)
    if resume_flag:
        return SessionOpenRequest(mode="resume_picker")
    return SessionOpenRequest(mode="new")

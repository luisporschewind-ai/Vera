"""Project RuntimeOutput into immutable timeline mutations."""

from __future__ import annotations

import shlex
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput, StreamFrame, StreamFrameType
from vera.presentation.diagnostics_copy import format_config_body, format_doctor_body
from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.errors import SideEffectFact
from vera.presentation.event_copy import (
    event_summary,
    event_title,
    format_recovery_inspection,
    format_tool_body,
    format_tool_title,
    is_silent,
)
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.status_panel import format_status_panel
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.presentation.timeline_time import should_omit_timeline_block
from vera.project_instructions import format_instruction_status
from vera.redaction import Redactor
from vera.session.models import SessionStatus

_SIDE_EFFECT_EVENTS = frozenset(
    {
        "changeset.applied",
        "verification.started",
        "verification.completed",
        "rollback.completed",
        "recovery.resumed",
    }
)


class AppendBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["append"] = "append"
    block: TimelineBlock


class UpdateBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["update"] = "update"
    block: TimelineBlock


class FocusBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["focus"] = "focus"
    block_id: str


TimelineMutation = Annotated[
    AppendBlock | UpdateBlock | FocusBlock,
    Field(discriminator="type"),
]


class TimelineProjector:
    """Pure RuntimeOutput → TimelineMutation projector."""

    def __init__(
        self,
        disclosure: DisclosurePolicy | None = None,
        *,
        max_body_bytes: int = 8_192,
        max_blocks: int = 200,
    ) -> None:
        self.disclosure = disclosure or DisclosurePolicy()
        self._redactor = Redactor()
        self._blocks: dict[str, TimelineBlock] = {}
        self._streams: dict[str, dict[str, object]] = {}
        self._tool_blocks: dict[tuple[str, str], str] = {}
        self._max_body_bytes = max_body_bytes
        self._max_blocks = max_blocks
        self._side_effect_runs: set[str] = set()
        self._model_failures: dict[str, dict[str, object]] = {}
        self._tool_started_at: dict[tuple[str, str], datetime] = {}

    def reset(self) -> None:
        self._blocks.clear()
        self._streams.clear()
        self._tool_blocks.clear()
        self._side_effect_runs.clear()
        self._model_failures.clear()
        self._tool_started_at.clear()

    def apply(self, output: RuntimeOutput) -> tuple[TimelineMutation, ...]:
        output = self._redactor.redact_output(output)
        if isinstance(output, StreamFrame):
            return self._apply_stream(output)
        return self._apply_event(output)

    def blocks(self) -> tuple[TimelineBlock, ...]:
        return tuple(self._blocks.values())

    def _apply_stream(self, frame: StreamFrame) -> tuple[TimelineMutation, ...]:
        if frame.type is not StreamFrameType.ASSISTANT_DELTA:
            return ()
        stream_key = f"{frame.run_id}:{frame.stream_id}"
        state = self._streams.setdefault(
            stream_key,
            {"next_index": 0, "text": "", "incomplete": False, "seen": set()},
        )
        seen_raw = state["seen"]
        seen: set[int] = seen_raw if isinstance(seen_raw, set) else set()
        state["seen"] = seen
        if frame.index in seen:
            return ()
        next_raw = state["next_index"]
        next_index = int(next_raw) if isinstance(next_raw, int) else 0
        if bool(state["incomplete"]) or frame.index != next_index:
            state["incomplete"] = True
            block_id = f"{frame.run_id}:{frame.stream_id}:assistant"
            existing = self._blocks.get(block_id)
            if existing is None:
                return ()
            updated = existing.model_copy(update={"incomplete": True})
            self._blocks[block_id] = updated
            return (UpdateBlock(block=updated),)
        seen.add(frame.index)
        state["next_index"] = frame.index + 1
        text = sanitize_terminal_text(str(frame.payload.get("text", "")))
        state["text"] = str(state["text"]) + text
        body, truncated = self._truncate_body(str(state["text"]))
        if truncated:
            state["text"] = body
        block_id = f"{frame.run_id}:{frame.stream_id}:assistant"
        existing = self._blocks.get(block_id)
        if existing is None:
            block = TimelineBlock(
                block_id=block_id,
                run_id=frame.run_id,
                kind=BlockKind.ASSISTANT,
                title="Vera",
                body=body,
                status=BlockStatus.RUNNING,
                expanded=self.disclosure.initial_state(BlockKind.ASSISTANT, BlockStatus.RUNNING),
                truncated=truncated,
            )
            self._blocks[block_id] = block
            return (AppendBlock(block=block),)
        updated = existing.model_copy(
            update={"body": body, "status": BlockStatus.RUNNING, "truncated": truncated}
        )
        self._blocks[block_id] = updated
        return (UpdateBlock(block=updated),)

    def _apply_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        handlers = {
            "run.started": self._status_event,
            "assistant.message": self._assistant_message,
            "tool.started": self._tool_started,
            "tool.completed": self._tool_completed,
            "changeset.proposed": self._changeset_proposed,
            "approval.required": self._approval_required,
            "approval.resolved": self._status_event,
            "approval.expired": self._approval_expired,
            "approval.invalidated": self._approval_expired,
            "checkpoint.created": self._status_event,
            "changeset.applied": self._changeset_applied,
            "verification.started": self._verification_started,
            "verification.completed": self._verification_completed,
            "run.completed": self._terminal_status,
            "run.failed": self._run_failed,
            "run.cancelled": self._run_cancelled,
            "recovery.detected": self._recovery_event,
            "recovery.manual_required": self._recovery_event,
            "conversation.compacted": self._status_event,
            "session.status": self._session_status,
            "session.message": self._session_message,
            "session.user_prompt": self._user_prompt,
            "session.help": self._session_message,
            "session.doctor": self._session_doctor,
            "session.theme": self._session_message,
            "session.shortcuts": self._session_message,
            "session.config": self._session_config,
            "session.usage": self._session_message,
            "session.permissions": self._session_message,
            "session.review": self._session_message,
            "session.diff": self._session_diff,
            "session.action_rejected": self._error_event,
            "session.closed": self._status_event,
            "session.persistence_changed": self._persistence_warning,
            "session.close_warning": self._persistence_warning,
            "session.loaded": self._session_loaded,
            "session.listed": self._session_message,
            "session.load_failed": self._persistence_warning,
            "project.instructions.loaded": self._instruction_status,
            "project.instructions.skipped": self._instruction_status,
            "project.instructions.status": self._instruction_status,
        }
        if event.type in _SIDE_EFFECT_EVENTS:
            self._side_effect_runs.add(event.run_id)
        if event.type == "model.failed":
            self._model_failures[event.run_id] = dict(event.payload)
        if is_silent(event.type):
            return ()
        handler = handlers.get(event.type, self._unknown_event)
        return self._with_occurred_at(handler(event), event.timestamp)

    def _with_occurred_at(
        self, mutations: tuple[TimelineMutation, ...], occurred_at: datetime
    ) -> tuple[TimelineMutation, ...]:
        stamped: list[TimelineMutation] = []
        for item in mutations:
            if isinstance(item, (AppendBlock, UpdateBlock)) and item.block.occurred_at is None:
                block = item.block.model_copy(
                    update={"occurred_at": occurred_at, "created_at": occurred_at}
                )
                self._blocks[block.block_id] = block
                item = item.model_copy(update={"block": block})
            stamped.append(item)
        return tuple(stamped)

    def _side_effects_for(self, run_id: str) -> SideEffectFact:
        """Only claim a side effect when a write or command event was observed."""

        return "workspace_changed" if run_id in self._side_effect_runs else "no_workspace_change"

    def _unapplied_diffs(self, run_id: str) -> tuple[TimelineMutation, ...]:
        """Keep proposal Diff visible, but never imply the workspace was written."""

        if run_id in self._side_effect_runs:
            return ()
        return self._relabel_diffs(run_id, title="Diff · 未写入", status=BlockStatus.FAILED)

    def _relabel_diffs(
        self,
        run_id: str,
        *,
        title: str,
        status: BlockStatus,
    ) -> tuple[TimelineMutation, ...]:
        mutations: list[TimelineMutation] = []
        for key, block in list(self._blocks.items()):
            if block.run_id != run_id or block.kind is not BlockKind.DIFF:
                continue
            updated = block.model_copy(
                update={
                    "title": sanitize_terminal_text(title),
                    "status": status,
                }
            )
            self._blocks[key] = updated
            mutations.append(UpdateBlock(block=updated))
        return tuple(mutations)

    def _changeset_applied(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._relabel_diffs(
            event.run_id,
            title="Diff · 已写入",
            status=BlockStatus.SUCCEEDED,
        ) + self._status_event(event)

    def _truncate_body(self, body: str) -> tuple[str, bool]:
        encoded = body.encode("utf-8")
        if len(encoded) <= self._max_body_bytes:
            return body, False
        clipped = encoded[: self._max_body_bytes].decode("utf-8", errors="ignore")
        return clipped, True

    def _evict_if_needed(self) -> None:
        protected = {BlockKind.APPROVAL, BlockKind.DIFF, BlockKind.ERROR, BlockKind.USER}
        while len(self._blocks) > self._max_blocks:
            victim = next(
                (key for key, block in self._blocks.items() if block.kind not in protected),
                None,
            )
            if victim is None:
                break
            del self._blocks[victim]

    def _append(
        self,
        *,
        block_id: str,
        run_id: str,
        kind: BlockKind,
        title: str,
        body: str,
        status: BlockStatus,
        focus: bool = False,
        ref_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> tuple[TimelineMutation, ...]:
        expanded = self.disclosure.initial_state(kind, status)
        clipped, truncated = self._truncate_body(sanitize_terminal_text(body))
        previous = next(reversed(self._blocks.values()), None) if self._blocks else None
        if should_omit_timeline_block(kind, title, clipped, previous=previous):
            return ()
        block = TimelineBlock(
            block_id=block_id,
            run_id=run_id,
            kind=kind,
            title=sanitize_terminal_text(title),
            body=clipped,
            status=status,
            expanded=expanded,
            truncated=truncated,
            ref_id=ref_id,
            occurred_at=occurred_at,
            created_at=occurred_at,
        )
        self._blocks[block_id] = block
        self._evict_if_needed()
        mutations: list[TimelineMutation] = [AppendBlock(block=block)]
        if focus:
            mutations.append(FocusBlock(block_id=block_id))
        return tuple(mutations)

    def _assistant_message(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        content = str(event.payload.get("content", event.payload.get("text", "")))
        stream_id = event.payload.get("stream_id")
        if isinstance(stream_id, str) and stream_id:
            block_id = f"{event.run_id}:{stream_id}:assistant"
            existing = self._blocks.get(block_id)
            if existing is not None:
                updated = existing.model_copy(
                    update={
                        "body": sanitize_terminal_text(content),
                        "status": BlockStatus.SUCCEEDED,
                        "incomplete": False,
                    }
                )
                self._blocks[block_id] = updated
                return (UpdateBlock(block=updated),)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:assistant",
            run_id=event.run_id,
            kind=BlockKind.ASSISTANT,
            title="Vera",
            body=content,
            status=BlockStatus.SUCCEEDED,
        )

    def _tool_started(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        name = str(event.payload.get("name", "tool"))
        block_id = f"{event.run_id}:{event.sequence}:tool"
        call_id = str(event.payload.get("call_id", event.sequence))
        target = str(event.payload.get("target") or "")
        self._tool_blocks[(event.run_id, call_id)] = block_id
        self._tool_blocks[(event.run_id, name)] = block_id
        self._tool_started_at[(event.run_id, call_id)] = event.timestamp
        return self._append(
            block_id=block_id,
            run_id=event.run_id,
            kind=BlockKind.TOOL,
            title=format_tool_title(name, target=target, status="running"),
            body=format_tool_body(target=target, status="running"),
            status=BlockStatus.RUNNING,
        )

    def _tool_completed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        name = str(event.payload.get("name", "tool"))
        ok = bool(event.payload.get("ok", True))
        status = BlockStatus.SUCCEEDED if ok else BlockStatus.FAILED
        call_id = str(event.payload.get("call_id", ""))
        target = str(event.payload.get("target") or "")
        started_at = self._tool_started_at.pop((event.run_id, call_id), None)
        duration_ms: int | None = None
        raw_duration = event.payload.get("duration_ms")
        if isinstance(raw_duration, int):
            duration_ms = raw_duration
        elif started_at is not None:
            duration_ms = max(0, int((event.timestamp - started_at).total_seconds() * 1000))
        status_key = "completed" if ok else "failed"
        error = str(event.payload.get("error") or "")
        error_code = str(event.payload.get("error_code") or "")
        truncated = bool(event.payload.get("truncated", False))
        body = format_tool_body(
            target=target,
            status=status_key,
            duration_ms=duration_ms,
            error=error,
            error_code=error_code,
            truncated=truncated,
        )
        title = format_tool_title(name, target=target, status=status_key, duration_ms=duration_ms)
        block_id = self._tool_blocks.get((event.run_id, call_id)) or self._tool_blocks.get(
            (event.run_id, name)
        )
        if block_id and block_id in self._blocks:
            existing = self._blocks[block_id]
            if not target:
                target = existing.body.partition("目标：")[2].split("\n", 1)[0]
                if target:
                    title = format_tool_title(
                        name, target=target, status=status_key, duration_ms=duration_ms
                    )
                    body = format_tool_body(
                        target=target,
                        status=status_key,
                        duration_ms=duration_ms,
                        error=error,
                        error_code=error_code,
                        truncated=truncated,
                    )
            updated = self.disclosure.on_status_change(existing, status).model_copy(
                update={
                    "title": sanitize_terminal_text(title),
                    "body": sanitize_terminal_text(body),
                }
            )
            self._blocks[block_id] = updated
            return (UpdateBlock(block=updated),)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:tool",
            run_id=event.run_id,
            kind=BlockKind.TOOL,
            title=title,
            body=body,
            status=status,
        )

    def _user_prompt(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        text = str(event.payload.get("text", ""))
        if not text.strip():
            return ()
        block = project_user_prompt(event.run_id, text, event.sequence, occurred_at=event.timestamp)
        self._blocks[block.block_id] = block
        self._evict_if_needed()
        return (AppendBlock(block=block),)

    def _changeset_proposed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        files = event.payload.get("files", [])
        parts: list[str] = []
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path", ""))
                diff = str(item.get("unified_diff", ""))
                parts.append(f"{path}\n{diff}".rstrip())
        body = "\n\n".join(parts)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:diff",
            run_id=event.run_id,
            kind=BlockKind.DIFF,
            title=f"Diff · {len(parts)} files",
            body=body,
            status=BlockStatus.PENDING,
        )

    def _session_diff(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        files = event.payload.get("files", [])
        text = str(event.payload.get("text") or "").strip()
        count = len(files) if isinstance(files, list) else 0
        body = text if text else "没有 Diff。"
        applied = event.payload.get("applied")
        if count and applied is False:
            title = f"Diff · {count} files · 未写入"
        elif count:
            title = f"Diff · {count} files"
        else:
            title = "Diff"
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:diff",
            run_id=event.run_id,
            kind=BlockKind.DIFF,
            title=title,
            body=sanitize_terminal_text(body),
            status=BlockStatus.FAILED if applied is False else BlockStatus.SUCCEEDED,
        )

    def _approval_required(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        risk = str(event.payload.get("risk", "unknown"))
        kind = str(event.payload.get("kind", "changeset"))
        approval_id = str(event.payload.get("approval_id", "unknown"))
        target = str(event.payload.get("target") or event.payload.get("target_id") or "")
        workspace = str(event.payload.get("workspace") or event.payload.get("workspace_root") or "")
        effect = str(
            event.payload.get("effect")
            or event.payload.get("description")
            or "批准后才会执行该动作"
        )
        argv = event.payload.get("argv", [])
        command = (
            shlex.join(str(part) for part in argv)
            if kind == "command" and isinstance(argv, list) and argv
            else ""
        )
        profile = event.payload.get("artifact_profile") if kind == "command" else None
        root = event.payload.get("artifact_root") if kind == "command" else None
        cwd = event.payload.get("cwd") if kind == "command" else None
        body = "\n".join(
            part
            for part in (
                f"动作 {kind}",
                f"命令 {command}" if command else "",
                f"Profile {profile}" if profile else "",
                f"产物根 {root}" if root else "",
                f"工作目录 {cwd}" if cwd else "",
                f"目标 {target}" if target and not command else "",
                f"风险 {risk}",
                f"工作区 {workspace}" if workspace else "",
                f"效果 {effect}",
            )
            if part
        )
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:approval",
            run_id=event.run_id,
            kind=BlockKind.APPROVAL,
            title=f"Approval required · {kind} · {risk}",
            body=sanitize_terminal_text(body),
            status=BlockStatus.PENDING,
            focus=True,
            ref_id=approval_id,
        )

    def _approval_expired(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        from vera.presentation.errors import format_failure_body

        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title="审批已过期",
            body=format_failure_body(event),
            status=BlockStatus.FAILED,
        )

    def _verification_started(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        argv = event.payload.get("argv", [])
        title = "Verification · running"
        body = " ".join(str(part) for part in argv) if isinstance(argv, list) else str(argv)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:verification",
            run_id=event.run_id,
            kind=BlockKind.VERIFICATION,
            title=title,
            body=body,
            status=BlockStatus.RUNNING,
        )

    def _verification_completed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        result = str(event.payload.get("status", "unknown"))
        failed = result not in {"passed", "ok", "succeeded"}
        status = BlockStatus.FAILED if failed else BlockStatus.SUCCEEDED
        block_id = f"{event.run_id}:{event.sequence}:verification"
        # Prefer updating the most recent verification block for this run.
        existing_id = next(
            (
                key
                for key, block in reversed(list(self._blocks.items()))
                if block.run_id == event.run_id and block.kind is BlockKind.VERIFICATION
            ),
            None,
        )
        body = sanitize_terminal_text(
            str(event.payload.get("stderr") or event.payload.get("stdout") or result)
        )
        if existing_id is not None:
            existing = self._blocks[existing_id]
            updated = self.disclosure.on_status_change(existing, status).model_copy(
                update={
                    "title": sanitize_terminal_text(
                        f"Verification · {'failed' if failed else 'passed'}"
                    ),
                    "body": body or existing.body,
                }
            )
            self._blocks[existing_id] = updated
            return (UpdateBlock(block=updated),)
        return self._append(
            block_id=block_id,
            run_id=event.run_id,
            kind=BlockKind.VERIFICATION,
            title=f"Verification · {'failed' if failed else 'passed'}",
            body=body,
            status=status,
        )

    def _run_failed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        from vera.presentation.errors import format_failure_body

        return self._unapplied_diffs(event.run_id) + self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title="任务失败",
            body=format_failure_body(
                event,
                side_effects=self._side_effects_for(event.run_id),
                diagnostics=self._model_failures.get(event.run_id),
            ),
            status=BlockStatus.FAILED,
        )

    def _run_cancelled(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        from vera.presentation.errors import format_failure_body

        return self._unapplied_diffs(event.run_id) + self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title="已取消",
            body=format_failure_body(
                event,
                side_effects=self._side_effects_for(event.run_id),
            ),
            status=BlockStatus.CANCELLED,
        )

    def _recovery_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        if event.type == "recovery.manual_required":
            from vera.presentation.errors import format_failure_body

            return self._append(
                block_id=f"{event.run_id}:{event.sequence}:error",
                run_id=event.run_id,
                kind=BlockKind.ERROR,
                title=event_title(event.type),
                body=format_failure_body(event),
                status=BlockStatus.FAILED,
            )
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:recovery",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event_title(event.type),
            body=format_recovery_inspection(event.run_id, event.payload),
            status=BlockStatus.SUCCEEDED,
        )

    def _error_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        from vera.presentation.errors import format_failure_body

        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title="Error",
            body=format_failure_body(event),
            status=BlockStatus.FAILED,
        )

    def _terminal_status(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._status_event(event)

    def _session_status(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        try:
            status = SessionStatus.model_validate(event.payload)
        except ValidationError:
            return self._session_message(event)
        body = format_status_panel(status)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event_title(event.type),
            body=sanitize_terminal_text(body),
            status=BlockStatus.SUCCEEDED,
        )

    def _session_doctor(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event_title(event.type),
            body=sanitize_terminal_text(format_doctor_body(event.payload)),
            status=BlockStatus.SUCCEEDED,
        )

    def _session_config(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event_title(event.type),
            body=sanitize_terminal_text(format_config_body(event.payload)),
            status=BlockStatus.SUCCEEDED,
        )

    def _session_message(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        if event.payload.get("clear_display"):
            return ()
        text = event.payload.get("text")
        if isinstance(text, str) and text.strip():
            body = text.strip()
            lines = body.splitlines()
            if len(lines) == 1:
                title = event_title(event.type)
            else:
                first = lines[0]
                title = first if len(first) <= 40 else first[:37] + "..."
        else:
            title = event_title(event.type)
            body = event_summary(event.payload)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=title,
            body=body,
            status=BlockStatus.SUCCEEDED,
        )

    def _persistence_warning(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        advice = event.payload.get("advice")
        if isinstance(advice, str) and advice.strip():
            body = advice.strip()
        else:
            body = event_summary(event.payload)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title=event_title(event.type),
            body=sanitize_terminal_text(body),
            status=BlockStatus.FAILED,
        )

    def _instruction_status(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        text = event.payload.get("text")
        if isinstance(text, str) and text.strip():
            body = text.strip()
        else:
            body = format_instruction_status(dict(event.payload))
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event_title(event.type),
            body=sanitize_terminal_text(body),
            status=BlockStatus.SUCCEEDED,
        )

    def _session_loaded(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        from vera.session.startup import HISTORY_DISPLAY_LIMIT

        items = event.payload.get("items") or []
        if not isinstance(items, list):
            items = []
        bounded = items[-HISTORY_DISPLAY_LIMIT:]
        mutations: list[TimelineMutation] = []
        for index, item in enumerate(bounded):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", ""))
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            kind = BlockKind.USER if role == "user" else BlockKind.ASSISTANT
            title = "你" if role == "user" else "Vera" if role == "assistant" else "摘要"
            stamp = item.get("timestamp")
            occurred_at = stamp if isinstance(stamp, datetime) else None
            mutations.extend(
                self._append(
                    block_id=f"{event.run_id}:{event.sequence}:hist:{index}",
                    run_id=event.run_id,
                    kind=kind,
                    title=title,
                    body=sanitize_terminal_text(content),
                    status=BlockStatus.SUCCEEDED,
                    occurred_at=occurred_at,
                )
            )
        return tuple(mutations)

    def _status_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event_title(event.type),
            body=event_summary(event.payload),
            status=BlockStatus.SUCCEEDED,
        )

    def _unknown_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._status_event(event)


def project_user_prompt(
    run_id: str,
    text: str,
    sequence: int = 0,
    *,
    created_at: datetime | None = None,
    occurred_at: datetime | None = None,
) -> TimelineBlock:
    policy = DisclosurePolicy()
    stamp = occurred_at if occurred_at is not None else created_at
    return TimelineBlock(
        block_id=f"{run_id}:{sequence}:user",
        run_id=run_id,
        kind=BlockKind.USER,
        title="用户",
        body=sanitize_terminal_text(text),
        status=BlockStatus.SUCCEEDED,
        expanded=policy.initial_state(BlockKind.USER, BlockStatus.SUCCEEDED),
        occurred_at=stamp,
        created_at=stamp,
    )

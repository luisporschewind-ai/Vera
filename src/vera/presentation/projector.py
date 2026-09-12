"""Project RuntimeOutput into immutable timeline mutations."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput, StreamFrame, StreamFrameType
from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.redaction import Redactor


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
                title="助手",
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
            "changeset.applied": self._status_event,
            "verification.started": self._verification_started,
            "verification.completed": self._verification_completed,
            "run.completed": self._terminal_status,
            "run.failed": self._run_failed,
            "run.cancelled": self._run_cancelled,
            "recovery.detected": self._recovery_event,
            "conversation.compacted": self._status_event,
            "session.status": self._status_event,
            "session.message": self._session_message,
            "session.help": self._session_message,
            "session.action_rejected": self._error_event,
            "session.closed": self._status_event,
        }
        handler = handlers.get(event.type, self._unknown_event)
        return handler(event)

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
    ) -> tuple[TimelineMutation, ...]:
        expanded = self.disclosure.initial_state(kind, status)
        clipped, truncated = self._truncate_body(sanitize_terminal_text(body))
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
            title="助手",
            body=content,
            status=BlockStatus.SUCCEEDED,
        )

    def _tool_started(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        name = str(event.payload.get("name", "tool"))
        block_id = f"{event.run_id}:{event.sequence}:tool"
        call_id = str(event.payload.get("call_id", event.sequence))
        self._tool_blocks[(event.run_id, call_id)] = block_id
        self._tool_blocks[(event.run_id, name)] = block_id
        return self._append(
            block_id=block_id,
            run_id=event.run_id,
            kind=BlockKind.TOOL,
            title=f"{name} · running",
            body="",
            status=BlockStatus.RUNNING,
        )

    def _tool_completed(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        name = str(event.payload.get("name", "tool"))
        ok = bool(event.payload.get("ok", True))
        status = BlockStatus.SUCCEEDED if ok else BlockStatus.FAILED
        call_id = str(event.payload.get("call_id", ""))
        block_id = self._tool_blocks.get((event.run_id, call_id)) or self._tool_blocks.get(
            (event.run_id, name)
        )
        body = sanitize_terminal_text(
            str(event.payload.get("error") or event.payload.get("result") or "")
        )
        if block_id and block_id in self._blocks:
            existing = self._blocks[block_id]
            updated = self.disclosure.on_status_change(existing, status).model_copy(
                update={
                    "title": sanitize_terminal_text(f"{name} · {'completed' if ok else 'failed'}"),
                    "body": body or existing.body,
                }
            )
            self._blocks[block_id] = updated
            return (UpdateBlock(block=updated),)
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:tool",
            run_id=event.run_id,
            kind=BlockKind.TOOL,
            title=f"{name} · {'completed' if ok else 'failed'}",
            body=body,
            status=status,
        )

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
        body = "\n".join(
            part
            for part in (
                f"动作 {kind}",
                f"目标 {target}" if target else "",
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

        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title="Run failed",
            body=format_failure_body(event),
            status=BlockStatus.FAILED,
        )

    def _run_cancelled(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        from vera.presentation.errors import format_failure_body

        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title="已取消",
            body=format_failure_body(event),
            status=BlockStatus.CANCELLED,
        )

    def _recovery_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        from vera.presentation.errors import format_failure_body

        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title="恢复",
            body=format_failure_body(event),
            status=BlockStatus.FAILED,
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

    def _session_message(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        text = str(event.payload.get("text", ""))
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title="Session",
            body=text,
            status=BlockStatus.SUCCEEDED,
        )

    def _status_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event.type,
            body=str(event.payload),
            status=BlockStatus.SUCCEEDED,
        )

    def _unknown_event(self, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
        return self._append(
            block_id=f"{event.run_id}:{event.sequence}:status",
            run_id=event.run_id,
            kind=BlockKind.STATUS,
            title=event.type,
            body=sanitize_terminal_text(str(event.payload)),
            status=BlockStatus.SUCCEEDED,
        )


def project_user_prompt(run_id: str, text: str, sequence: int = 0) -> TimelineBlock:
    policy = DisclosurePolicy()
    return TimelineBlock(
        block_id=f"{run_id}:{sequence}:user",
        run_id=run_id,
        kind=BlockKind.USER,
        title="用户",
        body=sanitize_terminal_text(text),
        status=BlockStatus.SUCCEEDED,
        expanded=policy.initial_state(BlockKind.USER, BlockStatus.SUCCEEDED),
    )

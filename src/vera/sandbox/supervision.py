"""One fail-closed process boundary shared by Bash, Git and verification."""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from vera.process.supervisor import ProcessRequest, ProcessResult, ProcessSupervisor
from vera.sandbox.access import AccessDenied, AccessSession, FilePermissions, ResourceIdentity
from vera.sandbox.backend import SandboxCleanupError, SandboxError
from vera.sandbox.files import current_permissions


class SandboxBackend(Protocol):
    def prepare(
        self, request: ProcessRequest, permissions: FilePermissions
    ) -> AbstractContextManager[ProcessRequest]: ...


class _Cancellation(threading.Event):
    def __init__(self, *events: threading.Event | None) -> None:
        super().__init__()
        self.events = events

    def is_set(self) -> bool:
        return super().is_set() or any(event.is_set() for event in self.events if event is not None)


class SandboxedSupervisor(ProcessSupervisor):
    def __init__(
        self,
        session: AccessSession,
        backend: SandboxBackend,
        *,
        delegate: ProcessSupervisor | None = None,
    ) -> None:
        super().__init__()
        self.session = session
        self.backend = backend
        self.delegate = delegate or ProcessSupervisor(strict_group=True)

    def run(
        self, request: ProcessRequest, *, cancel_event: threading.Event | None = None
    ) -> ProcessResult:
        return self._run(request, cancel_event=cancel_event)

    def run_artifact(
        self, request: ProcessRequest, root: Path, *, cancel_event: threading.Event | None = None
    ) -> ProcessResult:
        """Called only with the existing Core-approved, prepared artifact plan root."""
        return self._run(request, cancel_event=cancel_event, artifact_root=root)

    def _run(
        self,
        request: ProcessRequest,
        *,
        cancel_event: threading.Event | None = None,
        artifact_root: Path | None = None,
    ) -> ProcessResult:
        operation_id = hashlib.sha256(
            json.dumps(
                {"argv": request.argv, "cwd": str(request.cwd.resolve())}, sort_keys=True
            ).encode()
        ).hexdigest()
        completed: ProcessResult | None = None
        try:
            resources = self.session.command_resources(operation_id)
            active = current_permissions(self.session)
            context = (
                nullcontext(active)
                if active is not None
                else self.session.operation(operation_id, resources)
            )
            with context as permissions:
                if artifact_root is not None:
                    root = artifact_root.resolve(strict=True)
                    permissions = replace(
                        permissions,
                        readable=(*permissions.readable, root),
                        writable=(*permissions.writable, root),
                        identities=(*permissions.identities, ResourceIdentity.capture(root)),
                    )
                with self.backend.prepare(request, permissions) as wrapped:
                    permissions.validate()
                    cancelled = _Cancellation(cancel_event, permissions.revoked)
                    if cancelled.is_set():
                        return ProcessResult("cancelled", None, b"", b"")
                    completed = self.delegate.run(wrapped, cancel_event=cancelled)
                    completed = replace(completed, effective_argv=wrapped.effective_argv)
                    return completed
        except SandboxCleanupError as exc:
            if completed is None:
                return ProcessResult(
                    "error", None, b"", str(exc).encode(), cleanup_error="sandbox_cleanup_failed"
                )
            return replace(
                completed,
                status="error",
                stderr=completed.stderr + b"\n" + str(exc).encode(),
                cleanup_error="sandbox_cleanup_failed",
            )
        except (AccessDenied, SandboxError) as exc:
            return ProcessResult("error", None, b"", str(exc).encode())

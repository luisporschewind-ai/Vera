import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from vera.process.supervisor import ProcessRequest, ProcessResult
from vera.sandbox.access import AccessSession


def test_revoke_terminates_real_parent_and_child(tmp_path: Path) -> None:
    """Process lifecycle integration, not proof of OS file/network isolation."""
    from vera.sandbox.supervision import SandboxedSupervisor

    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "fake.txt"
    outside.write_text("fake")
    session = AccessSession(work)
    request = session.request(outside, "read", "session")
    grant = session.resolve(request.request_id, approved=True)
    assert grant is not None

    class Backend:
        @contextmanager
        def prepare(self, request, permissions):
            assert outside in permissions.readable
            yield request

    helper = Path(__file__).resolve().parents[1] / "process/helpers/spawn_child.py"
    pid_file = work / "pids.txt"
    results = []
    supervisor = SandboxedSupervisor(session, Backend())
    cancel = threading.Event()
    worker = threading.Thread(
        target=lambda: results.append(
            supervisor.run(
                ProcessRequest(
                    (
                        sys.executable,
                        str(helper),
                        "--grandchild",
                        "--ignore-term",
                        "--sleep",
                        "20",
                        "--pid-file",
                        str(pid_file),
                    ),
                    work,
                    {},
                    8,
                ),
                cancel_event=cancel,
            )
        )
    )
    worker.start()
    pids = []
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if pid_file.exists():
                pids = [int(value) for value in pid_file.read_text().splitlines()]
                if len(pids) == 2:
                    break
            time.sleep(0.02)
        assert len(pids) == 2
        for pid in pids:
            os.kill(pid, 0)
        session.revoke(grant.grant_id)
        worker.join(4)
        assert not worker.is_alive()
        assert results[0].status == "cancelled"
        assert results[0].group_managed

        def alive(pid):
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(alive(pid) for pid in pids):
            time.sleep(0.05)
        assert not any(alive(pid) for pid in pids)
    finally:
        cancel.set()
        worker.join(10)


def test_backend_failure_never_calls_process_delegate(tmp_path: Path) -> None:
    from vera.sandbox.backend import SandboxError
    from vera.sandbox.supervision import SandboxedSupervisor

    class Backend:
        @contextmanager
        def prepare(self, request, permissions):
            raise SandboxError("sandbox_unavailable")
            yield

    class Delegate:
        def run(self, *args, **kwargs):
            raise AssertionError("unconfined fallback")

    supervisor = SandboxedSupervisor(AccessSession(tmp_path), Backend(), delegate=Delegate())
    result = supervisor.run(ProcessRequest(("echo", "no"), tmp_path, {}, 1))
    assert result.status == "error"
    assert result.stderr == b"sandbox_unavailable"


def test_shared_supervisor_observes_session_revocation(tmp_path: Path) -> None:
    from vera.sandbox.supervision import SandboxedSupervisor

    workspace = tmp_path / "work"
    workspace.mkdir()
    outside = tmp_path / "file"
    outside.write_text("fake")
    session = AccessSession(workspace)
    req = session.request(outside, "read", "session")
    grant = session.resolve(req.request_id, approved=True)

    class Backend:
        @contextmanager
        def prepare(self, request, permissions):
            assert outside in permissions.readable
            yield request

    class Delegate:
        def run(self, request, *, cancel_event):
            assert not cancel_event.is_set()
            session.revoke(grant.grant_id)
            assert cancel_event.is_set()
            return ProcessResult("cancelled", -15, b"", b"")

    result = SandboxedSupervisor(session, Backend(), delegate=Delegate()).run(
        ProcessRequest(("echo", "no"), workspace, {}, 1)
    )
    assert result.status == "cancelled"

"""Read-only SRT diagnostic for a temporary, empty CoreSimulator device set."""

from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from vera.process.supervisor import ProcessRequest
from vera.sandbox.access import AccessSession
from vera.sandbox.backend import SrtBackend
from vera.sandbox.settings import SandboxSettings
from vera.sandbox.supervision import SandboxedSupervisor

ROOT = Path("/private/tmp/vera-0089-acceptance.psEsZR")
if "--run-fake-probe" not in sys.argv:
    raise SystemExit("Add --run-fake-probe to explicitly run this crash-prone diagnostic")
CONFIG = SandboxSettings.model_validate_json((ROOT / "config/sandbox.json").read_text())
SERVICES = (
    "com.apple.CoreSimulator.CoreSimulatorService",
    "com.apple.CoreSimulator.simdiskimaged",
    "com.apple.FileCoordination",
    "com.apple.FSEvents",
    "com.apple.CoreServices.coreservicesd",
    "com.apple.cfprefsd.agent",
    "com.apple.cfprefsd.daemon",
)


class DiagnosticBackend(SrtBackend):
    @contextmanager
    def prepare(self, request, permissions):
        with super().prepare(request, permissions) as wrapped:
            argv = list(wrapped.argv)
            index = argv.index("/usr/bin/sandbox-exec") + 2
            argv[index] += "".join(
                f"\n(allow mach-lookup (global-name {json.dumps(service)}))"
                for service in SERVICES
            )
            yield replace(wrapped, argv=tuple(argv))


with tempfile.TemporaryDirectory(prefix="ios-service-probe-", dir=ROOT) as raw:
    fixture = Path(raw)
    workspace = fixture / "workspace"
    workspace.mkdir()
    device_set = workspace / "empty-device-set"
    device_set.mkdir()
    session = AccessSession(workspace)
    try:
        backend = DiagnosticBackend(
            developer_dir=Path("/Applications/Xcode.app/Contents/Developer"),
            runtime_root=CONFIG.runtime_root,
            node=CONFIG.node,
            base_readable=(
                *CONFIG.base_readable,
                Path("/Applications/Xcode.app"),
                Path("/usr/share/firmlinks"),
                Path("/Library/Preferences/com.apple.dt.Xcode.plist"),
                Path("/Library/Developer/PrivateFrameworks"),
                Path("/Library/Apple/System/Library/PrivateFrameworks"),
            ),
        )
        result = SandboxedSupervisor(session, backend).run(
            ProcessRequest(
                argv=(
                    "/Applications/Xcode.app/Contents/Developer/usr/bin/simctl",
                    "--set",
                    str(device_set),
                    "list",
                    "runtimes",
                ),
                cwd=workspace,
                env={},
                timeout_seconds=30,
            )
        )
        print(
            json.dumps(
                {
                    "services": SERVICES,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout.decode(errors="replace")[:2000],
                    "stderr": result.stderr.decode(errors="replace")[:2000],
                    "device_set_children": len(tuple(device_set.iterdir())),
                    "cleanup_error": result.cleanup_error,
                },
                ensure_ascii=False,
            )
        )
    finally:
        session.close()

"""One unsigned generic iOS build of a disposable fake-project copy."""

from __future__ import annotations

import json
import shutil
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


class DiagnosticBackend(SrtBackend):
    @contextmanager
    def prepare(self, request, permissions):
        with super().prepare(request, permissions) as wrapped:
            argv = list(wrapped.argv)
            index = argv.index("/usr/bin/sandbox-exec") + 2
            for service in (
                "com.apple.CoreSimulator.CoreSimulatorService",
                "com.apple.CoreSimulator.simdiskimaged",
                "com.apple.FileCoordination",
                "com.apple.FSEvents",
                "com.apple.CoreServices.coreservicesd",
            ):
                argv[index] += (
                    f"\n(allow mach-lookup (global-name {json.dumps(service)}))"
                )
            yield replace(wrapped, argv=tuple(argv))

ROOT = Path("/private/tmp/vera-0089-acceptance.psEsZR")
if "--run-fake-probe" not in sys.argv:
    raise SystemExit("Add --run-fake-probe to explicitly run this diagnostic")
CONFIG = SandboxSettings.model_validate_json((ROOT / "config/sandbox.json").read_text())

with tempfile.TemporaryDirectory(prefix="ios-build-services-", dir=ROOT) as raw:
    fixture = Path(raw)
    workspace = fixture / "workspace"
    shutil.copytree(
        ROOT / "real-projects-g21oo820/VeraTestDemo",
        workspace,
        ignore=shutil.ignore_patterns(".git", ".DS_Store"),
    )
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
                    "/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild",
                    "-project",
                    "VeraTestDemo.xcodeproj",
                    "-scheme",
                    "VeraTestDemo",
                    "-configuration",
                    "Debug",
                    "-sdk",
                    "iphoneos",
                    "-destination",
                    "generic/platform=iOS",
                    "-derivedDataPath",
                    str(workspace / "DerivedData"),
                    "CODE_SIGNING_ALLOWED=NO",
                    "CODE_SIGNING_REQUIRED=NO",
                    "CODE_SIGN_IDENTITY=",
                    "build",
                ),
                cwd=workspace,
                env={},
                timeout_seconds=120,
                max_output_bytes=200_000,
            )
        )
        stderr = result.stderr.decode(errors="replace")
        stdout = result.stdout.decode(errors="replace")
        print(
            json.dumps(
                {
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "cleanup_error": result.cleanup_error,
                    "build_succeeded": "** BUILD SUCCEEDED **" in stdout + stderr,
                    "build_failed": "** BUILD FAILED **" in stdout + stderr,
                    "simulator_error_mentions": stderr.count("CoreSimulatorService"),
                    "platform_not_installed": "Platform Not Installed" in stdout + stderr,
                    "stdout_tail": stdout[-1700:],
                    "stderr_tail": stderr[-1700:],
                },
                ensure_ascii=False,
            )
        )
    finally:
        session.close()

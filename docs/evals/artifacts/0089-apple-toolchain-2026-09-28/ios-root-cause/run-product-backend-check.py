import json
import shutil
import tempfile
from pathlib import Path

from vera.process.supervisor import ProcessRequest
from vera.sandbox.access import AccessSession
from vera.sandbox.backend import SrtBackend
from vera.sandbox.settings import SandboxSettings
from vera.sandbox.supervision import SandboxedSupervisor

acceptance = Path('/private/tmp/vera-0089-acceptance.psEsZR')
source = acceptance / 'real-projects-g21oo820/VeraTestDemo'
config = SandboxSettings.model_validate_json((acceptance / 'config/sandbox.json').read_text())
fixture = Path(tempfile.mkdtemp(prefix='ios-product-check-', dir=acceptance))
# Keep Core's sparse image in this fresh, owned fixture so cleanup is measurable.
tempfile.tempdir = str(fixture)
workspace = fixture / 'workspace'
shutil.copytree(source, workspace, ignore=shutil.ignore_patterns('.git', '.DS_Store', 'DerivedData'))

device = Path('/Library/Developer/CoreSimulator/Profiles/DeviceTypes/iPhone 16e.simdevicetype')
runtime = Path('/Library/Developer/CoreSimulator/Volumes/iOS_23A343/Library/Developer/Profiles/Runtimes/iOS 26.0.simruntime')
# Correct the runtime bundle path used by the installed host.
runtime = Path('/Library/Developer/CoreSimulator/Volumes/iOS_23A343/Library/Developer/CoreSimulator/Profiles/Runtimes/iOS 26.0.simruntime')
extra_reads = (
    Path('/Applications/Xcode.app'), Path('/usr/share/firmlinks'),
    Path('/Library/Preferences/com.apple.dt.Xcode.plist'),
    Path('/Library/Developer/PrivateFrameworks'),
    Path('/Library/Apple/System/Library/PrivateFrameworks'), device, runtime,
    Path('/usr/share/icu/icudt76l.dat'),
)
list_directories = tuple(sorted({
    parent for bundle in (device, runtime) for parent in bundle.parents if parent != Path('/')
}))
backend = SrtBackend(
    runtime_root=config.runtime_root, node=config.node,
    base_readable=(*config.base_readable, *extra_reads),
    developer_dir=Path('/Applications/Xcode.app/Contents/Developer'),
    directory_listable=list_directories,
)
session = AccessSession(workspace)
runner = SandboxedSupervisor(session, backend)
argv = (
    '/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild',
    '-project', 'VeraTestDemo.xcodeproj', '-scheme', 'VeraTestDemo',
    '-configuration', 'Debug', '-sdk', 'iphoneos',
    '-destination', 'generic/platform=iOS', 'CODE_SIGNING_ALLOWED=NO',
    'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY=', 'build',
)
try:
    result = runner.run(ProcessRequest(
        argv=argv, cwd=workspace, env={}, timeout_seconds=180,
        max_output_bytes=1_000_000, apple_ios_build_services=True,
    ))
    output = (result.stdout + result.stderr).decode(errors='replace')
    report = {
        'build_status': result.status, 'exit_code': result.exit_code,
        'cleanup_error': result.cleanup_error,
        'build_succeeded_marker': '** BUILD SUCCEEDED **' in output,
        'build_failed_marker': '** BUILD FAILED **' in output,
        'effective_argv': result.effective_argv,
        'remaining_product_volumes': [str(p) for p in fixture.glob('vera-apple-build-*')],
        'interesting_output': [line for line in output.splitlines() if '** BUILD ' in line or 'error:' in line or 'Operation not permitted' in line][-30:],
    }
    (acceptance / 'product-backend-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    assert result.status == 'exited' and result.exit_code == 0
    assert result.cleanup_error is None
    assert report['build_succeeded_marker']
    assert not report['remaining_product_volumes']
    denied = runner.run(ProcessRequest(
        argv=('/bin/cat', '/private/etc/passwd'), cwd=workspace, env={}, timeout_seconds=10,
    ))
    boundary = {
        'outside_read_status': denied.status, 'outside_read_exit_code': denied.exit_code,
        'outside_read_denied': denied.status == 'exited' and denied.exit_code != 0,
    }
    (acceptance / 'product-boundary-check.json').write_text(json.dumps(boundary, indent=2) + '\n')
    print(json.dumps(boundary))
    assert boundary['outside_read_denied']
finally:
    session.close()
    shutil.rmtree(fixture, ignore_errors=True)

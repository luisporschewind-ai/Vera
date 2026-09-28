import json
import shutil
import sys
from contextlib import contextmanager
from dataclasses import replace
import tempfile
from pathlib import Path
from vera.process.supervisor import ProcessSupervisor
from dataclasses import asdict
from vera.sandbox.settings import SandboxSettings
from vera.sandbox.access import AccessSession
from vera.sandbox.backend import SrtBackend
from vera.sandbox.supervision import SandboxedSupervisor
from vera.verification.runner import VerificationRunner
from vera.verification.artifacts import VerificationArtifactPlanner
from vera.contracts.verification import VerificationCommand

root = Path('/private/tmp/vera-0089-acceptance.psEsZR')
fixture = Path(tempfile.mkdtemp(prefix='verification-xcode-', dir=root))
work = fixture / 'workspace'
work.mkdir()
(work/'VeraProbe.xcodeproj').mkdir()
(work/'VeraProbe.xcodeproj/project.pbxproj').write_bytes((root/'native-probe.pbxproj').read_bytes())
(work/'main.c').write_text('int main(void) { return 0; }\n')
config = SandboxSettings.model_validate_json((root / 'config/sandbox.json').read_text())
toolchain = Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr')
sdk = Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
llbuild = Path('/Applications/Xcode.app/Contents/SharedFrameworks/llbuild.framework/Versions/A/llbuild')
extra = tuple(Path(p) for p in ('/Applications/Xcode.app','/usr/share/firmlinks','/Library/Preferences/com.apple.dt.Xcode.plist','/Library/Developer/PrivateFrameworks','/Library/Apple/System/Library/PrivateFrameworks'))
class EvidenceSupervisor(ProcessSupervisor):
 def run(self, request, **kwargs):
  result=super().run(request, **kwargs)
  data=asdict(result);data['stdout']=result.stdout.decode(errors='replace');data['stderr']=result.stderr.decode(errors='replace')
  (fixture/'process-result.json').write_text(json.dumps(data,indent=2))
  return result
session = AccessSession(work)
supervisor = SandboxedSupervisor(session, SrtBackend(developer_dir=Path("/Applications/Xcode.app/Contents/Developer"), runtime_root=config.runtime_root, node=config.node, base_readable=(*config.base_readable, toolchain, sdk, llbuild, *extra)), delegate=EvidenceSupervisor(strict_group=True))
prefix = fixture / 'artifacts'
planner = VerificationArtifactPlanner(prefix=prefix)
command = planner.plan(VerificationCommand(argv=('/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild', '-project', 'VeraProbe.xcodeproj', '-target', 'VeraProbe', '-configuration', 'Debug', '-sdk', 'macosx', 'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY=', 'build'), timeout_seconds=300), workspace_root=work, installation_id='fake-0089', run_id='xcode-build', index=0)
if '--diagnostic-developer-dir' in sys.argv:
    command = command.model_copy(update={'argv': ('/usr/bin/env', 'DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer', *command.argv)})
print('FIXTURE:', fixture, flush=True)
print('PLAN:', command.model_dump_json(), flush=True)
try:
    result = VerificationRunner(work, supervisor=supervisor, artifact_prefix=prefix).run(command)
    facts = {'diagnostic_developer_dir': '--diagnostic-developer-dir' in sys.argv, 'fixture': str(fixture), 'command': command.model_dump(mode='json'), 'result': result.model_dump(mode='json'), 'artifact_removed': not Path(command.artifact_plan.root).exists(), 'workspace_build_absent': not (work / '.build').exists()}
    (fixture / 'result.json').write_text(json.dumps(facts, indent=2))
    print(json.dumps(facts, indent=2), flush=True)
finally:
    session.close()

"""Offline fake-workspace acceptance of the production planner and SRT runner."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from vera.contracts.verification import VerificationCommand
from vera.process.supervisor import ProcessRequest, ProcessSupervisor
from vera.sandbox.access import AccessSession
from vera.sandbox.backend import SrtBackend
from vera.sandbox.settings import SandboxSettings
from vera.sandbox.supervision import SandboxedSupervisor
from vera.verification.artifacts import VerificationArtifactPlanner, VerificationArtifactRoot
from vera.verification.runner import VerificationRunner, workspace_file_fingerprint

base = Path('/private/tmp/vera-0089-acceptance.psEsZR')
fixture = Path(tempfile.mkdtemp(prefix='formal-verification-', dir=base))
work = fixture / 'workspace'
work.mkdir()
(work / 'bin').mkdir()
ruff = work / 'bin/ruff'
shutil.copy2('/Users/admin/Vera/.venv/bin/ruff', ruff)
(work / 'good.py').write_text('answer = 42\n')
(work / 'bad.py').write_text('print(UNDEFINED_INSIDE_ONLY)\n')
outside = fixture / 'outside.py'
outside.write_text('print(OUTSIDE_SENTINEL_FAKE)\n')
config = SandboxSettings.model_validate_json((base / 'config/sandbox.json').read_text())
session = AccessSession(work)
supervisor = SandboxedSupervisor(session, SrtBackend(
    runtime_root=config.runtime_root, node=config.node, base_readable=config.base_readable))
prefix = fixture / 'artifacts'
planner = VerificationArtifactPlanner(prefix=prefix)
snap = workspace_file_fingerprint(work)
facts = {'fixture': str(fixture), 'cases': [], 'tool_sha256': hashlib.sha256(ruff.read_bytes()).hexdigest()}

class ObservedRoots(VerificationArtifactRoot):
    def cleanup(self, root, *, workspace_root):
        report = Path(root) / 'report.json'
        self.report_existed = report.is_file()
        self.report = json.loads(report.read_text()) if report.is_file() else None
        return super().cleanup(root, workspace_root=workspace_root)

try:
    baseline = ProcessSupervisor().run(ProcessRequest(
        (str(ruff), 'check', '--isolated', '--no-cache', '--output-format', 'json', str(outside)),
        work, {'PATH': '/usr/bin:/bin'}, 15))
    facts['outside_baseline'] = {'exit_code': baseline.exit_code,
        'contains_marker': 'OUTSIDE_SENTINEL_FAKE' in baseline.stdout.decode()}
    assert facts['outside_baseline'] == {'exit_code': 1, 'contains_marker': True}
    for index, (name, target, expected) in enumerate([
        ('success', 'good.py', 'passed'), ('failure', 'bad.py', 'failed'),
        ('outside_read_denied', str(outside), 'failed')]):
        original = VerificationCommand(argv=(str(ruff), 'check', '--isolated', '--output-format', 'json', target), timeout_seconds=15)
        plan_args = dict(workspace_root=work, installation_id='fake-formal-0089', run_id=name, index=index)
        preview = planner.plan(original, **plan_args)
        report = Path(preview.artifact_plan.root) / 'report.json'
        command = planner.plan(original.model_copy(update={'argv': (*original.argv, '--output-file', str(report))}), **plan_args)
        roots = ObservedRoots(prefix=prefix)
        result = VerificationRunner(work, supervisor=supervisor, artifact_prefix=prefix, artifact_roots=roots).run(command)
        item = {'case': name, 'command': command.model_dump(mode='json'), 'result': result.model_dump(mode='json'),
            'report_existed_before_cleanup': roots.report_existed, 'report': roots.report,
            'artifact_removed': not Path(command.artifact_plan.root).exists(),
            'workspace_unchanged': workspace_file_fingerprint(work) == snap}
        facts['cases'].append(item)
        (fixture / 'result.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2))
        print(json.dumps(item, ensure_ascii=False), flush=True)
        assert result.status == expected, result
        assert result.artifact_cleanup_status == 'cleaned' and not result.workspace_mutations
        assert item['artifact_removed'] and item['workspace_unchanged'] and roots.report_existed
        if name == 'success':
            assert result.exit_code == 0 and roots.report == []
        elif name == 'failure':
            assert any(row['code'] == 'F821' for row in roots.report)
        else:
            rendered = json.dumps(roots.report)
            assert 'Operation not permitted' in rendered and 'OUTSIDE_SENTINEL_FAKE' not in rendered
    facts['passed'] = True
    print('PASS: production planner -> real SRT -> runner results -> observed report -> cleanup; workspace unchanged', flush=True)
finally:
    session.close()
    (fixture / 'result.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2))
    print('EVIDENCE:', fixture / 'result.json', flush=True)

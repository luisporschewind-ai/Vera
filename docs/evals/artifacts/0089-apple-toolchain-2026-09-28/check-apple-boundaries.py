import json,tempfile
from pathlib import Path
from vera.sandbox.settings import SandboxSettings
from vera.sandbox.backend import SrtBackend
from vera.sandbox.access import AccessSession
from vera.sandbox.supervision import SandboxedSupervisor
from vera.process.supervisor import ProcessRequest
base=Path('/private/tmp/vera-0089-acceptance.psEsZR');root=Path(tempfile.mkdtemp(prefix='apple-boundary-',dir=base));work=root/'workspace';work.mkdir();(work/'inside.txt').write_text('INSIDE_ONLY\n');(root/'outside.txt').write_text('OUTSIDE_ONLY\n')
c=SandboxSettings.model_validate_json((base/'config/sandbox.json').read_text());extra=tuple(Path(p) for p in ('/Applications/Xcode.app','/usr/share/firmlinks','/Library/Preferences/com.apple.dt.Xcode.plist','/Library/Developer/PrivateFrameworks','/Library/Apple/System/Library/PrivateFrameworks'))
session=AccessSession(work);sup=SandboxedSupervisor(session,SrtBackend(runtime_root=c.runtime_root,node=c.node,base_readable=(*c.base_readable,*extra),developer_dir=Path('/Applications/Xcode.app/Contents/Developer')))
facts={}
for name,argv in [('inside',('/bin/cat','inside.txt')),('outside',('/bin/cat','../outside.txt')),('write',('/bin/cp','inside.txt','../denied.txt')),('child',('/usr/bin/find','.','-name','inside.txt','-exec','/bin/cat','../outside.txt',';'))]:
 r=sup.run(ProcessRequest(argv,work,{},5));facts[name]={'status':r.status,'exit_code':r.exit_code,'stdout':r.stdout.decode(),'stderr':r.stderr.decode()}
facts['outside_unchanged']=(root/'outside.txt').read_text()=='OUTSIDE_ONLY\n';facts['write_absent']=not(root/'denied.txt').exists();session.close();(root/'result.json').write_text(json.dumps(facts,indent=2));print(root);print(json.dumps(facts,indent=2))

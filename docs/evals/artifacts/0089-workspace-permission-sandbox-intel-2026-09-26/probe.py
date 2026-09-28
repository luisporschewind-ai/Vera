from pathlib import Path
import json, socket, subprocess
from vera.sandbox.backend import SrtBackend
from vera.sandbox.access import FilePermissions
from vera.process.supervisor import ProcessRequest, ProcessSupervisor
root=Path(__file__).parent; w=root/'workspace'; outside=root/'outside'
(w/'inside.txt').write_text('inside fake data\n'); (outside/'a.txt').write_text('outside fake A\n'); (outside/'b.txt').write_text('outside fake B\n')
(w/'escape').symlink_to(outside/'a.txt')
base=tuple(map(Path,('/System','/usr/lib','/usr/bin','/bin','/dev/null','/dev/urandom')))
b=SrtBackend(runtime_root=root/'node_modules/@anthropic-ai/sandbox-runtime',base_readable=base)
rows=[]
def run(name,argv,read=(),write=()):
 p=FilePermissions(w,(w,*read),(w,*write))
 with b.prepare(ProcessRequest(tuple(argv),w,{},3),p) as req:
  result=ProcessSupervisor().run(req)
 rows.append({'name':name,'status':result.status,'exit':result.exit_code,'stdout':result.stdout.decode(errors='replace'),'stderr':result.stderr.decode(errors='replace')})
run('inside read write',['/bin/sh','-c','cat inside.txt && echo ok > result.txt && cat result.txt'])
run('outside read',['/bin/cat',str(outside/'a.txt')])
run('outside write',['/bin/sh','-c','echo bad > '+str(outside/'new.txt')])
run('symlink escape',['/bin/cat','escape'])
run('descendant escape',['/bin/sh','-c','/bin/sh -c "cat '+str(outside/'a.txt')+'"'])
run('grant A read',['/bin/cat',str(outside/'a.txt')],read=(outside/'a.txt',))
run('grant A cannot read B',['/bin/cat',str(outside/'b.txt')],read=(outside/'a.txt',))
run('grant A cannot write A',['/bin/sh','-c','echo bad > '+str(outside/'a.txt')],read=(outside/'a.txt',))
run('grant A write',['/bin/sh','-c','echo approved > '+str(outside/'a.txt')],read=(outside/'a.txt',),write=(outside/'a.txt',))
with socket.socket() as server:
 server.bind(('127.0.0.1',0)); server.listen(2); port=server.getsockname()[1]
 baseline=subprocess.run(['/usr/bin/nc','-z','-G','1','127.0.0.1',str(port)],capture_output=True,timeout=2)
 rows.append({'name':'loopback baseline','exit':baseline.returncode})
 run('network blocked',['/usr/bin/nc','-z','-G','1','127.0.0.1',str(port)])
(root/'probe-results.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
assert not (outside/'new.txt').exists()

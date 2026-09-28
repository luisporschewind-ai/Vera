from pathlib import Path
import json,socket,subprocess
from vera.sandbox.backend import SrtBackend
from vera.sandbox.access import FilePermissions
from vera.process.supervisor import ProcessRequest,ProcessSupervisor
root=Path(__file__).parent; w=root/'workspace'
b=SrtBackend(runtime_root=root/'node_modules/@anthropic-ai/sandbox-runtime',base_readable=tuple(map(Path,('/System','/usr/lib','/usr/bin','/bin','/dev/null','/dev/urandom'))))
rows=[]
for label,family,host in [('ipv4',socket.AF_INET,'127.0.0.1'),('ipv6',socket.AF_INET6,'::1')]:
 with socket.socket(family) as server:
  server.bind(host if family==socket.AF_UNIX else (host,0)); server.listen(2)
  argv=('/usr/bin/nc','-z','-v','-G','1',*(('-U',host) if family==socket.AF_UNIX else (host,str(server.getsockname()[1]))))
  baseline=subprocess.run(argv,capture_output=True,timeout=2,env={'PATH':'/usr/bin:/bin','HOME':str(root/'home')})
  with b.prepare(ProcessRequest(argv,w,{},2),FilePermissions(w,(w,),(w,))) as req:
   result=ProcessSupervisor(strict_group=True).run(req)
  row={'case':label,'baseline_exit':baseline.returncode,'sandbox_exit':result.exit_code,'stderr':result.stderr.decode()}
  rows.append(row)
  assert baseline.returncode==0,row
  assert result.exit_code!=0 and 'Operation not permitted' in row['stderr'],row
(root/'network-results.json').write_text(json.dumps(rows,indent=2)); print(json.dumps(rows,indent=2))

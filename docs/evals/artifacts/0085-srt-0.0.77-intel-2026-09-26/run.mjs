import fs from 'node:fs';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {SandboxManager as S, SandboxRuntimeConfigSchema as Schema} from './install/node_modules/@anthropic-ai/sandbox-runtime/dist/index.js';
const root='/private/tmp/vera-srt-probe._mev9a5n';
const evidence=root+'/evidence';
const config=Schema.parse(JSON.parse(fs.readFileSync(root+'/config.json','utf8')));
const q=s=>"'"+s.replaceAll("'","'\\''")+"'";
const binary=root+'/artifacts/probe';
const results=[];const groups=new Set();
let server;let started=0;
const record=r=>{results.push(r);fs.writeFileSync(evidence+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(r));};
function launch(cmd,limit=15000,expected=0,id='command',cancel=false){
 return new Promise((resolve,reject)=>{
  const child=spawn('/bin/bash',['-c',cmd],{cwd:root+'/workspace',env:process.env,detached:true,stdio:['ignore','pipe','pipe']});
  groups.add(child.pid);let stdout='',stderr='',timedOut=false;
  child.stdout.on('data',b=>stdout+=b);child.stderr.on('data',b=>stderr+=b);
  const kill=()=>{try{process.kill(-child.pid,'SIGKILL')}catch(e){if(e.code!=='ESRCH')throw e}};
  const timer=setTimeout(()=>{timedOut=true;kill()},limit);
  const cancelTimer=cancel?setTimeout(()=>{try{process.kill(-child.pid,'SIGTERM')}catch{}},800):null;
  child.on('error',reject);
  child.on('close',(code,signal)=>{
   clearTimeout(timer);clearTimeout(cancelTimer);
   // Always reap any still-live process group belonging to this invocation.
   kill();groups.delete(child.pid);
   const r={id,pid:child.pid,code,signal,timedOut,stdout,stderr};record(r);
   if(timedOut || (!cancel&&code!==expected))reject(new Error('gate failed: '+id));else resolve(r);
  });
 });
}
async function wrapped(cmd,id,expected=0,limit=15000,cancel=false){
 if(started && Date.now()-started>300000)throw Error('execution budget exceeded');
 const s=await S.wrapWithSandbox(cmd,'/bin/bash',undefined,undefined,{commandId:id});
 if(!s.includes('/usr/bin/sandbox-exec'))throw Error('sandbox wrapper absent');
 fs.writeFileSync(evidence+'/'+id+'.command',s,{mode:0o600});
 return launch(s,limit,expected,id,cancel);
}
try {
 await S.initialize(config,undefined,false);
 const preview=await S.wrapWithSandbox('/usr/bin/true','/bin/bash',undefined,undefined,{commandId:'preview'});
 fs.writeFileSync(evidence+'/preview.command',preview,{mode:0o600});
 console.log('PROFILE_READY: inspect evidence/preview.command; enter RUN to execute.');
 await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('review timeout')),90000);process.stdin.once('data',d=>{clearTimeout(t);d.toString().trim()==='RUN'?resolve():reject(Error('not approved'))});process.stdin.resume()});
 started=Date.now();
 const watchdog=setTimeout(()=>{for(const pid of groups){try{process.kill(-pid,'SIGKILL')}catch{}}process.exit(124)},300000);watchdog.unref();
 await wrapped('/bin/echo shell-ok; /usr/bin/git --version && /usr/bin/xcrun --find clang','native-tools');
 await wrapped('/usr/bin/xcrun clang '+q(root+'/workspace/probe.c')+' -o '+q(binary)+' && '+q(binary),'compile-run',0,60000);
 await launch(q(binary)+' read '+q(root+'/outside/secret'),15000,0,'unconfined-fake-read');
 await wrapped(q(binary)+' read '+q(root+'/workspace/in-scope'),'workspace-read');
 await wrapped(q(binary)+' write '+q(root+'/artifacts/allowed'),'artifacts-write');
 await wrapped('/bin/sh -c '+q(q(binary)+' read '+q(root+'/outside/secret')),'grandchild-secret-denied',13);
 await wrapped(q(binary)+' write '+q(root+'/outside/blocked'),'outside-write-denied',13);
 await wrapped(q(binary)+' read '+q(root+'/workspace/secret-link'),'symlink-denied',13);
 server=http.createServer((req,res)=>{res.writeHead(200);res.end('VERA_LOOPBACK_OK')});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;
 await launch(q(binary)+' connect '+port,15000,0,'live-loopback-baseline');
 await wrapped(q(binary)+' connect '+port,'direct-loopback-denied',13);
 const curl='/usr/bin/curl --silent --show-error --max-time 4 --noproxy '+q('')+' ';
 const url='http://127.0.0.1:'+port+'/';
 const denied=await wrapped(curl+q(url),'proxy-default-denied');
 if(!/blocked|denied/i.test(denied.stdout))throw Error('proxy deny evidence absent');
 const allow={...config,network:{...config.network,allowedDomains:['127.0.0.1:'+port]}};
 S.updateConfig(allow);
 const allowed=await wrapped(curl+q(url),'proxy-granted');
 if(allowed.stdout!=='VERA_LOOPBACK_OK')throw Error('proxy positive failed');
 const other=await wrapped(curl+q('http://localhost:'+port+'/'),'proxy-other-name-denied');
 if(!/blocked|denied/i.test(other.stdout))throw Error('other hostname unexpectedly allowed');
 S.updateConfig(config);
 const pidfile=root+'/artifacts/descendant.pid';
 await wrapped('/bin/sh -c '+q('/bin/sleep 8 & echo $! > '+q(pidfile)+'; wait'),'supervised-cancel',0,15000,true);
 const pid=Number(fs.readFileSync(pidfile,'utf8').trim());
 let exists=true;try{process.kill(pid,0)}catch(e){if(e.code==='ESRCH')exists=false;else throw e}
 record({id:'descendant-after-cancel',pid,exists});if(exists)throw Error('descendant remains');
 const cli=root+'/install/node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js';
 fs.writeFileSync(root+'/invalid.json','{');
 const sentinel=root+'/artifacts/should-not-exist';
 await launch('/usr/local/bin/node '+q(cli)+' --settings '+q(root+'/invalid.json')+' /usr/bin/touch '+q(sentinel),15000,1,'invalid-config');
 await launch('/usr/local/bin/node '+q(cli)+' --settings '+q(root+'/missing.json')+' /usr/bin/touch '+q(sentinel),15000,1,'missing-config');
 if(fs.existsSync(sentinel))throw Error('fail-closed sentinel was created');
 record({id:'minimum-probe',status:'passed',seconds:(Date.now()-started)/1000});
} catch(e) {record({id:'minimum-probe',status:'stopped',error:String(e)});process.exitCode=1;}
finally {
 for(const pid of groups){try{process.kill(-pid,'SIGKILL')}catch{}}
 if(server)await new Promise(r=>server.close(r));
 await S.reset();process.stdin.pause();
 console.log('runtime-proxies-closed');
}

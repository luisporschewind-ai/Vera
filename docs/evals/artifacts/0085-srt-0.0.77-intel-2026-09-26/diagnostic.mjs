import fs from 'node:fs';
import {spawn} from 'node:child_process';
import {SandboxManager as S, SandboxRuntimeConfigSchema as Schema} from './install/node_modules/@anthropic-ai/sandbox-runtime/dist/index.js';
const root='/private/tmp/vera-srt-probe._mev9a5n';
const config=Schema.parse(JSON.parse(fs.readFileSync(root+'/config.json','utf8')));
let pid;
try {
 await S.initialize(config,undefined,false);
 const wrapped=await S.wrapWithSandbox('/usr/bin/git --version && /usr/bin/xcrun --find clang','/bin/bash',undefined,undefined,{commandId:'developer-dir-diagnostic'});
 if(!wrapped.includes('/usr/bin/sandbox-exec'))throw Error('missing sandbox');
 fs.writeFileSync(root+'/evidence/developer-dir-diagnostic.command',wrapped,{mode:0o600});
 await new Promise((resolve,reject)=>{
  const child=spawn('/bin/bash',['-c',wrapped],{env:process.env,cwd:root+'/workspace',detached:true,stdio:['ignore','pipe','pipe']});pid=child.pid;
  let stdout='',stderr='';child.stdout.on('data',b=>stdout+=b);child.stderr.on('data',b=>stderr+=b);
  const timer=setTimeout(()=>{try{process.kill(-pid,'SIGKILL')}catch{}},15000);
  child.on('error',reject);child.on('close',(code,signal)=>{clearTimeout(timer);const result={id:'developer-dir-diagnostic',pid,code,signal,stdout,stderr};fs.writeFileSync(root+'/evidence/developer-dir-diagnostic.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));if(code!==0)process.exitCode=1;resolve()});
 });
} finally {if(pid){try{process.kill(-pid,'SIGKILL')}catch{}}await S.reset();console.log('diagnostic-proxies-closed');}

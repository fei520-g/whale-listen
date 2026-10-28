import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {runtimeDocument} from '../room/dsh_room_agent.mjs';

test('isolated stdio worker uses dedicated preset and returns only bounded replies',async()=>{
  const base=path.dirname(fileURLToPath(import.meta.url));
  const tempRoot=path.resolve(base,'../testing/tmp');fs.mkdirSync(tempRoot,{recursive:true});
  const tmp=fs.mkdtempSync(path.join(tempRoot,'dsh-room-fake-'));
  try{
    for(const dir of ['src/music','state','roles','workspace'])fs.mkdirSync(path.join(tmp,dir),{recursive:true});
    fs.writeFileSync(path.join(tmp,'package.json'),JSON.stringify({type:'module'}));
    fs.writeFileSync(path.join(tmp,'config.json'),JSON.stringify({dsh:{baseUrl:'http://127.0.0.1',profile:'fake'}}));
    fs.writeFileSync(path.join(tmp,'state/current-role.json'),JSON.stringify({role:'whale',mode:'active'}));
    fs.writeFileSync(path.join(tmp,'roles/whale.md'),'示例角色，仅供测试');
    fs.writeFileSync(path.join(tmp,'src/dsh-auth.js'),`export async function buildDshAuthHeaders(){return {authHeaders:{}}}`);
    fs.writeFileSync(path.join(tmp,'src/learning-dsh.js'),`export function verifyLearningGuard(){return true}`);
    fs.writeFileSync(path.join(tmp,'src/music/music-state.mjs'),`export function readMusic(){return {available:false}}`);
    fs.writeFileSync(path.join(tmp,'src/dsh-client.js'),`
      export function unwrap(v){return v}
      export function createTurnCollector(){return {push:e=>e.type==='turn/end'?e.data:null}}
      export class NodeApiClient {
       constructor(){this.activeMux={ended:false,waitFollow:async()=>{}};this.q=[];this.wake=null;
        this.sessions={create:async r=>({sessionId:r.sessionId,agentPreset:r.agentPreset}),cancel:async()=>{},
         prompt:async r=>{this.q.push({payload:{type:'session/event',sessionId:r.sessionId,event:{type:'turn/end',data:{reason:{kind:'completed'},text:'["你好呀"]'}}}});this.wake?.();return {}}};
        this.events={mux:async function*(_,signal,onOpen){onOpen();signal.addEventListener('abort',()=>this.wake?.());while(!signal.aborted){if(this.q.length){yield this.q.shift();continue;}await new Promise(r=>{this.wake=r})}}.bind(this)};
       }
       async call(){return {agentPreset:'whale-kugou-chat',content:process.env.TEST_ROOM_PRESET}}
       subscribeSession(){}
      }`);
    const worker=path.resolve(base,'../room/dsh_worker.mjs');
    const child=spawn(process.execPath,[worker],{env:{...process.env,WHALE_BRIDGE_ROOT:tmp,WHALE_ROOM_WORKSPACE:path.join(tmp,'workspace'),TEST_ROOM_PRESET:runtimeDocument()},stdio:['pipe','pipe','pipe']});
    let output='',errors='';child.stdout.on('data',c=>output+=c);child.stderr.on('data',c=>errors+=c);
    child.stdin.end('{"version":1,"action":"start"}\n{"version":1,"action":"reply","text":"你好"}\n{"version":1,"action":"stop"}\n');
    const [code]=await once(child,'exit');assert.equal(code,0,errors);
    const records=output.trim().split('\n').map(JSON.parse);
    assert.deepEqual(records,[{ok:true,state:'ready'},{ok:true,messages:['你好呀']},{ok:true,state:'stopped'}]);
    assert.ok(!output.includes('示例角色'));assert.ok(!output.includes('你好"'));
  }finally{
    const expected=fs.realpathSync(tempRoot), target=fs.realpathSync(tmp);
    if(!target.startsWith(expected+path.sep))throw new Error('temporary directory escaped workspace');
    fs.rmSync(target,{recursive:true,force:true});
  }
});

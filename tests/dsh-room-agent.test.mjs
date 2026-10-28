import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRoomAgent,PRESET,runtimeDocument,validateReply} from '../room/dsh_room_agent.mjs';

function fixture({preset=runtimeDocument(),response='["你好呀","一起听歌"]',reason='completed',audio=null}={}) {
  const calls=[],queue=[];let wake;
  const notify=()=>{if(wake){wake();wake=null;}};
  const api={
    activeMux:{ended:false,waitFollow:async()=>calls.push('follow')},
    call:async()=>({agentPreset:PRESET,content:preset}),
    subscribeSession:id=>calls.push('subscribe'),
    sessions:{
      create:async request=>(calls.push('create'),{sessionId:request.sessionId,agentPreset:request.agentPreset}),
      prompt:async request=>{calls.push('prompt');calls.push(request.content[0].text);const value=Array.isArray(response)?response.shift():response;queue.push({payload:{type:'session/event',sessionId:request.sessionId,event:{type:'turn/end',data:{reason:{kind:reason},text:value}}}});notify();return {};},
      cancel:async()=>calls.push('cancel'),
    },
    events:{mux:async function*(_,signal,onOpen){onOpen();signal.addEventListener('abort',notify);while(!signal.aborted){if(queue.length){yield queue.shift();continue;}await new Promise(resolve=>{wake=resolve;});}}},
  };
  let lastMessage;
  const agent=createRoomAgent({api,unwrap:x=>x,createTurnCollector:()=>({push:e=>e.type==='turn/end'?{reason:e.data.reason,text:e.data.text}:null}),
    readRole:async()=> '角色资料',readMusic:async()=>({available:true,active:true,title:'歌曲',artist:'歌手',playbackState:'playing',secret:'not forwarded'}),readAudio:async()=>audio,
    verifyGuard:async()=>calls.push('guard'),cwd:'/isolated',timeoutMs:2000});
  return {api,agent,calls};
}

test('separate confirmed preset and follow before one prompt',async()=>{
  const {agent,calls}=fixture();await agent.start();
  assert.deepEqual(await agent.complete('你好'),['你好呀','一起听歌']);
  assert.ok(calls.indexOf('follow')<calls.indexOf('prompt'));assert.equal(calls.filter(x=>x==='prompt').length,1);
  await agent.close();
});
test('changed preset is rejected before creating a session',async()=>{
  const {agent,calls}=fixture({preset:'different'});await assert.rejects(agent.start(),/unsafe_room_preset/);
  assert.ok(!calls.includes('create'));
});
test('invalid model output is never sent and session is cancelled',async()=>{
  const {agent,calls}=fixture({response:'not json'});await agent.start();
  await assert.rejects(agent.complete('你好'),/invalid_agent_json/);assert.ok(calls.includes('cancel'));await agent.close();
});
test('a malformed completed response gets one format-only retry without sending it',async()=>{
  const {agent,calls}=fixture({response:['不是 JSON','["你好呀"]']});await agent.start();
  assert.deepEqual(await agent.complete('你好'),['你好呀']);
  assert.equal(calls.filter(x=>x==='prompt').length,2);assert.ok(!calls.includes('cancel'));await agent.close();
});
test('repeated malformed responses stop after one retry',async()=>{
  const {agent,calls}=fixture({response:['不是 JSON','依然不是 JSON']});await agent.start();
  await assert.rejects(agent.complete('你好'),/invalid_agent_json/);
  assert.equal(calls.filter(x=>x==='prompt').length,2);assert.ok(calls.includes('cancel'));await agent.close();
});
test('noncompleted turn is never treated as a reply',async()=>{
  const {agent}=fixture({reason:'error'});await agent.start();
  await assert.rejects(agent.complete('你好'),/agent_turn_incomplete/);await agent.close();
});
test('audio evidence is bounded and only appears for a music question',async()=>{
 const audio={version:1,analyzedAtMs:Date.now(),analysis:{status:'ok',rms_dbfs:-14,bpm_candidate:72.1,key_candidate:'C# major',extra:'secret'}};
 const {agent,calls}=fixture({audio});await agent.start();await agent.complete('你听到这段了吗');
 const text=calls.find(x=>typeof x==='string'&&x.includes('audioEvidence'));
 assert.ok(text.includes('72.1'));assert.ok(!text.includes('secret'));assert.ok(text.includes('不保证与当前歌曲对应'));await agent.close();
});
test('safe alternate model reply shapes retain all text',()=>{
 assert.deepEqual(validateReply('"你好呀"'),['你好呀']);
 assert.deepEqual(validateReply('{"messages":["一","二"]}'),['一','二']);
 assert.deepEqual(validateReply('["一","二","三","四"]'),['一\n二\n三\n四']);
 assert.deepEqual(validateReply('["一"," ","二"]'),['一','二']);
});
test('unrecognized or oversized outputs still fail safely',()=>{
 for(const v of ['{}','{"messages":["一"],"other":"x"}','[123]','[]',JSON.stringify(['x'.repeat(301)]),JSON.stringify(['x'.repeat(300),'y'.repeat(300),'z'.repeat(300),'q'.repeat(300)])])assert.throws(()=>validateReply(v),/invalid_agent_parts/);
});

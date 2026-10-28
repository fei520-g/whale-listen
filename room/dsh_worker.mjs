// Independent stdio model worker. It never sends room/QQ messages, and is not
// started by the deployed idle controller. Install only after preset review.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import {pathToFileURL} from 'node:url';
import {createRoomAgent} from './dsh_room_agent.mjs';

const root=process.env.WHALE_BRIDGE_ROOT;
const cwd=process.env.WHALE_ROOM_WORKSPACE;
if(!root||!cwd||!path.isAbsolute(root)||!path.isAbsolute(cwd))throw new Error('room worker paths not configured');
const bridge=path.resolve(root);
const load=async relative=>import(pathToFileURL(path.join(bridge,relative)).href);
const [{NodeApiClient,unwrap,createTurnCollector},{buildDshAuthHeaders},{verifyLearningGuard},{readMusic}]=await Promise.all([
  load('src/dsh-client.js'),load('src/dsh-auth.js'),load('src/learning-dsh.js'),load('src/music/music-state.mjs')
]);
const settings=JSON.parse(fs.readFileSync(path.join(bridge,'config.json'),'utf8'));
const api=new NodeApiClient(settings.dsh.baseUrl,120000,{authHeaders:(await buildDshAuthHeaders(settings)).authHeaders});
function role(){
  const state=JSON.parse(fs.readFileSync(path.join(bridge,'state/current-role.json'),'utf8'));
  if(typeof state.role!=='string'||!/^[\w\u4e00-\u9fff-]{1,80}$/.test(state.role))throw new Error('role_unavailable');
  const dir=fs.realpathSync(path.join(bridge,'roles'));
  const candidate=path.join(dir,state.role+'.md');
  if(!fs.lstatSync(candidate).isFile()||fs.realpathSync(candidate)!==candidate)throw new Error('role_unavailable');
  return fs.readFileSync(candidate,'utf8').slice(0,16000);
}
function audio(){
 const target='/var/lib/whale-audio-evidence/latest.json';let fd;
 try{fd=fs.openSync(target,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);const st=fs.fstatSync(fd);
  if(!st.isFile()||st.size>2048)return null;
  return JSON.parse(fs.readFileSync(fd,'utf8'));
 }catch{return null;}finally{if(fd!==undefined)fs.closeSync(fd);}
}
const agent=createRoomAgent({api,unwrap,createTurnCollector,readRole:role,readMusic,readAudio:audio,
  verifyGuard:()=>verifyLearningGuard(settings.dsh.dshHome,settings.dsh.profile||'desktop'),cwd});
const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
let ready=false;
try{
  for await(const line of lines){
    try{
      if(Buffer.byteLength(line)>16384)throw new Error('request_too_large');
      const request=JSON.parse(line);
      if(request?.version!==1||typeof request.action!=='string')throw new Error('invalid_request');
      if(request.action==='start'&&Object.keys(request).length===2&&!ready){await agent.start();ready=true;process.stdout.write('{"ok":true,"state":"ready"}\n');}
      else if(request.action==='reply'&&Object.keys(request).length===3&&ready){
        const messages=await agent.complete(request.text);process.stdout.write(JSON.stringify({ok:true,messages})+'\n');
      }else if(request.action==='stop'&&Object.keys(request).length===2){await agent.close();process.stdout.write('{"ok":true,"state":"stopped"}\n');break;}
      else throw new Error('invalid_request');
    }catch(error){
      // Record only a fixed classification, never message text or model output.
      const allowed=new Set(['invalid_agent_output','invalid_agent_json','invalid_agent_parts','agent_turn_incomplete','agent_reply_timeout','unsafe_room_preset','role_unavailable','room_agent_unavailable','event_stream_error','event_stream_closed','event_stream_unavailable','event_open_timeout']);
      const code=allowed.has(error?.message)?error.message:'other';
      const shapes=new Set(['non_array','too_many_parts','non_string_part','control_character','empty_reply','part_too_long','combined_too_long']);
      const detail=shapes.has(error?.detail)?error.detail:null;
      try{fs.writeFileSync(path.join(cwd,'last-audio-chat-error.json'),JSON.stringify({code,detail,at:Date.now()}),{mode:0o600});}catch{}
      process.stdout.write('{"ok":false,"error":"room_agent_unavailable"}\n');
      // A model/session failure may have an unknown result; fail closed.
      break;
    }
  }
}finally{await agent.close();lines.close();}

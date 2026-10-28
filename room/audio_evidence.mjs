// Experimental adapter: metadata only; never treats a musical guess as fact.
const MUSIC_QUESTION=/听|音乐|歌曲|这首|这段|旋律|节奏|曲子/;
const finite=(x,min,max)=>typeof x==='number'&&Number.isFinite(x)&&x>=min&&x<=max?x:null;
const KEY=/^(?:A|B|C|D|E|F|G)(?:#|b)? (?:major|minor)$/;
export function audioEvidence(record,{now=Date.now(),message=''}={}){
 if(typeof message!=='string'||!MUSIC_QUESTION.test(message)||!record||record.version!==1)return null;
 const stamp=finite(record.analyzedAtMs,0,9e15);
 if(stamp===null||stamp>now+5000||now-stamp>90000)return null;
 const a=record.analysis;
 if(!a||a.status!=='ok')return null;
 const rms=finite(a.rms_dbfs,-120,0);
 if(rms===null)return null;
 const tempo=finite(a.bpm_candidate,30,300);
 const key=typeof a.key_candidate==='string'&&KEY.test(a.key_candidate)?a.key_candidate:null;
 return {source:'用户主动采集的约8秒音频，由独立工具估计',ageSeconds:Math.max(0,Math.floor((now-stamp)/1000)),
   rmsDbfs:rms,bpmCandidate:tempo,keyCandidate:key,
   limitations:'仅是短片段的推测，不保证与当前歌曲对应；不说明人声、乐器、歌词或情绪。没有直接音频输入。'};
}

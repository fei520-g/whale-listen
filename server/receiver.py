"""Forced SSH command: accept one bounded music-state JSON line, never a shell command."""
import argparse,datetime,json,math,os,re,signal,sys,tempfile,time
from pathlib import Path
PACKAGES={'com.kugou.android','com.kugou.android.lite'}
STATES={'playing','paused','buffering','stopped','unknown'}
MAX_BYTES=16384

def text(value,limit):
 if value is None:return ''
 if not isinstance(value,str) or len(value)>limit:raise ValueError('invalid_text')
 return ''.join(c for c in value if ord(c)>=32 and ord(c)!=127).strip()

def number(value,lo,hi,nullable=False):
 if value is None and nullable:return None
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('invalid_number')
 return value

def validate(v,device,now_ms):
 if not isinstance(v,dict) or v.get('version')!=1 or not re.fullmatch(r'[a-z0-9-]{1,48}',device):raise ValueError('invalid_protocol')
 active=v.get('active');state=v.get('state')
 if not isinstance(active,bool) or state not in STATES:raise ValueError('invalid_state')
 package=v.get('package','')
 if active and package not in PACKAGES:raise ValueError('unsupported_player')
 observed=number(v.get('observedAtMs'),0,1e15)
 if abs(now_ms-observed)>15*60*1000:raise ValueError('phone_clock_out_of_range')
 result={'version':1,'deviceId':device,'receivedAtMs':now_ms,'observedAtMs':observed,'active':active,'package':package if active else '',
  'state':state if active else 'stopped','title':text(v.get('title'),240) if active else '',
  'artist':text(v.get('artist'),240) if active else '', 'album':text(v.get('album'),240) if active else '',
  'positionMs':number(v.get('positionMs'),0,7*24*3600*1000,True) if active else None,
  'durationMs':number(v.get('durationMs'),0,7*24*3600*1000,True) if active else None,
  'speed':number(v.get('speed',0),0,4) if active else 0}
 # Reject unknown text fields, including instructions and notification contents.
 allowed={'version','active','package','state','title','artist','album','positionMs','durationMs','speed','observedAtMs'}
 if set(v)-allowed:raise ValueError('unexpected_fields')
 if result['positionMs'] is not None and result['durationMs'] and result['positionMs']>result['durationMs']+30000:raise ValueError('invalid_position')
 return result

def write_state(directory,value):
 directory=Path(directory);directory.mkdir(mode=0o750,parents=True,exist_ok=True)
 data=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
 fd,name=tempfile.mkstemp(prefix='.music-',dir=directory)
 try:
  os.fchmod(fd,0o640)
  with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
  os.replace(name,directory/'current.json')
 finally:
  if os.path.exists(name):os.unlink(name)

def main():
 p=argparse.ArgumentParser();p.add_argument('--device',required=True);p.add_argument('--state-dir',default='/var/lib/whale-music/state');a=p.parse_args()
 if hasattr(signal,'SIGALRM'):signal.alarm(12)
 try:
  raw=sys.stdin.buffer.readline(MAX_BYTES+1)
  if len(raw)>MAX_BYTES or not raw.endswith(b'\n'):raise ValueError('payload_too_large_or_unterminated')
  value=validate(json.loads(raw),a.device,int(time.time()*1000));write_state(a.state_dir,value)
  print(json.dumps({'ok':True,'receivedAtMs':value['receivedAtMs']},separators=(',',':')))
 except (ValueError,TypeError,json.JSONDecodeError) as e:
  print(json.dumps({'ok':False,'error':str(e)[:80],'serverTimeMs':int(time.time()*1000)}));return 2
 return 0
if __name__=='__main__':sys.exit(main())

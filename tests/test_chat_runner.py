import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'room'))
from control import Store
from room_daemon import Supervisor
from native_room import NativeRoomClient
from chat_gate import ChatGate
from chat_outbox import Outbox
from chat_runner import ChatRunner
from worker_client import WorkerClient

LINK='https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code='+'b'*32
class FakeWorker:
    def __init__(self):self.calls=[];self.closed=False
    def complete(self,text):self.calls.append(text);return ['hello']
    def close(self):self.closed=True

class RunnerTests(unittest.TestCase):
    def setUp(self):
        p=Path(__file__).resolve().parents[1]/'testing/tmp';p.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=p);self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.store=Store(root/'control.sqlite',chat_available=True)
        self.members=[{'userid':789,'role':1},{'userid':123,'role':2,'nickname':'Whale','img':''}]
        self.operations=[];self.workers=[];self.rows=[];self.counter=0
        def transport(op,p,b):
            self.operations.append(op)
            if op=='status':return {'status':1,'data':{'status':1,'me_online':1,'eid':'987'}}
            if op=='heartbeat':return {'status':1,'data':{}}
            if op=='chat':return {'status':1,'data':{'msgid':999}}
            self.fail('unexpected operation')
        self.client=NativeRoomClient({'platform':'ordinary','userid':123,'token':'test-only-token','mid':'a'*32},transport=transport)
        reader=lambda _:{'roomid':'456','members':len(self.members),'member_data':self.members}
        self.supervisor=Supervisor(self.store,self.client,reader,hashlib.sha256(b'789').hexdigest())
        self.command('join',invite=LINK);self.supervisor.step()
        self.gate=ChatGate(root/'gate.sqlite',clock=lambda:1000);outbox=Outbox(root/'outbox.sqlite')
        def factory():w=FakeWorker();self.workers.append(w);return w
        self.runner=ChatRunner(self.supervisor,self.gate,outbox,lambda *_:{'status':1,'errcode':0,'list':self.rows},factory)
    def command(self,action,**kw):
        self.counter+=1
        return self.supervisor.control(dict(version=1,action=action,request_id=f'request-{self.counter:016}',expected_revision=self.store.read()['revision'],**kw))
    def test_no_worker_until_chat_enabled_then_one_new_message(self):
        self.runner.step();self.assertEqual(self.workers,[])
        self.command('chat');self.runner.step();self.assertEqual(len(self.workers),1)
        self.rows=[{'msgid':'1','uid':789,'addtime':1000,'tag':'genting:456','message':{'msgtype':801,'alert':'hello','sysMsg':0}}]
        self.runner.step();self.assertEqual(self.workers[0].calls,['hello']);self.assertEqual(self.operations.count('chat'),1)
        self.command('pause');self.runner.step();self.assertTrue(self.workers[0].closed)
    def test_extra_member_pauses_and_closes_worker(self):
        self.command('chat');self.runner.step();self.members.append({'userid':999,'role':2})
        self.assertEqual(self.runner.step()['state'],'paused_after_error')
        self.assertEqual(self.store.public()['reply_mode'],'paused');self.assertTrue(self.workers[0].closed)
    def test_failed_worker_pauses_without_calling_model(self):
        self.command('chat');self.runner.worker_factory=lambda:(_ for _ in ()).throw(RuntimeError('unavailable'))
        self.assertEqual(self.runner.step()['state'],'paused_after_error')
        self.assertEqual(self.store.public()['reply_mode'],'paused')
        self.assertEqual(self.operations.count('chat'),0)
    def test_room_to_subprocess_to_send_with_fake_dependencies(self):
        program='''import sys,json
for line in sys.stdin:
 r=json.loads(line)
 if r['action']=='start':out={'ok':True,'state':'ready'}
 elif r['action']=='reply':out={'ok':True,'messages':['a','b']}
 else:out={'ok':True,'state':'stopped'}
 print(json.dumps(out),flush=True)
 if r['action']=='stop':break
'''
        self.runner.worker_factory=lambda:WorkerClient([sys.executable,'-u','-c',program],env=dict(os.environ),timeout=5)
        self.command('chat');self.runner.step()
        self.rows=[{'msgid':'1','uid':789,'addtime':1000,'tag':'genting:456','message':{'msgtype':801,'alert':'hello','sysMsg':0}}]
        self.runner.step();self.assertEqual(self.operations.count('chat'),2)
        self.runner.step();self.assertEqual(self.operations.count('chat'),2)
        self.command('pause');self.runner.step()

if __name__=='__main__':unittest.main()

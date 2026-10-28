import hashlib
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
from chat_session import ChatSession
from ordinary_room import RoomError

LINK='https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code='+'b'*32
class SessionTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[1]/'testing'/'tmp';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.store=Store(root/'control.sqlite',chat_available=True)
        self.calls=[];self.models=[];self.now=1000
        self.members=[{'userid':789,'role':1},{'userid':123,'role':2,'nickname':'Whale','img':''}]
        def native(op,params,body):
            self.calls.append(op)
            if op=='status':return {'status':1,'data':{'status':1,'me_online':1,'eid':'987'}}
            if op=='heartbeat':return {'status':1,'data':{}}
            if op=='chat':return {'status':1,'data':{'msgid':'999'}}
            self.fail('unexpected operation')
        client=NativeRoomClient({'platform':'ordinary','userid':123,'token':'test-only-token','mid':'a'*32},transport=native)
        self.pub=lambda _:{'roomid':'456','members':len(self.members),'member_data':self.members}
        self.supervisor=Supervisor(self.store,client,self.pub,hashlib.sha256(b'789').hexdigest())
        self.count=0
        self.command('join',invite=LINK);self.supervisor.step();self.command('chat')
        self.rows=[]
        def history(*_):return {'status':1,'errcode':0,'list':list(self.rows)}
        def complete(text):self.models.append(text);return ['你好','一起听']
        self.gate=ChatGate(root/'gate.sqlite',clock=lambda:self.now)
        self.chat=ChatSession(self.supervisor,self.gate,Outbox(root/'outbox.sqlite'),history,complete)
    def command(self,action,**kw):
        self.count+=1
        return self.supervisor.control(dict(version=1,action=action,request_id=f'command-{self.count:016}',expected_revision=self.store.read()['revision'],**kw))
    def msg(self,mid=1):
        return {'msgid':str(mid),'uid':789,'addtime':1000,'tag':'genting:456','message':{'msgtype':801,'alert':'hello','sysMsg':0}}
    def test_baseline_new_message_duplicate_and_no_spontaneous_model(self):
        self.chat.tick();self.assertEqual(self.models,[])
        self.rows=[self.msg()];r=self.chat.tick()
        self.assertEqual(r['received'],1);self.assertEqual(self.models,['hello']);self.assertEqual(self.calls.count('chat'),2)
        self.chat.tick();self.assertEqual(self.models,['hello']);self.assertEqual(self.calls.count('chat'),2)
    def test_user_leave_during_model_prevents_send(self):
        self.chat.tick();self.rows=[self.msg()]
        self.chat.complete=lambda _:(self.command('leave') or ['hello'])
        # Return a valid answer after the leave command, not the command receipt.
        def complete(_):self.command('leave');return ['hello']
        self.chat.complete=complete
        self.chat.tick();self.assertNotIn('chat',self.calls)
        self.assertFalse(self.store.public()['present'])
    def test_new_participant_before_send_blocks_message(self):
        self.chat.tick();self.rows=[self.msg()]
        def complete(_):self.members.append({'userid':999,'role':2});return ['hello']
        self.chat.complete=complete
        with self.assertRaises(RoomError):self.chat.tick()
        self.assertNotIn('chat',self.calls)
    def test_pause_stops_polling_and_model(self):
        self.chat.tick();self.command('pause');self.rows=[self.msg()]
        self.assertEqual(self.chat.tick()['state'],'paused');self.assertEqual(self.models,[])
    def test_uses_verified_incremental_query_after_baseline(self):
        self.rows=[self.msg(1)];calls=[]
        def newest(client,room,cursor):
            calls.append(cursor)
            return {'status':1,'errcode':0,'list':[self.msg(2)]}
        self.chat.newest=newest
        self.chat.tick();self.assertEqual(self.models,[])
        self.chat.tick();self.assertEqual(calls,['1']);self.assertEqual(self.models,['hello'])

if __name__=='__main__':unittest.main()

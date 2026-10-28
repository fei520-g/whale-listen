from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'room'))
from chat_outbox import Outbox, message_body
from native_room import NativeRoomClient
from ordinary_room import RoomError


class OutboxTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(__file__).resolve().parents[1] / 'testing' / 'tmp'
        tmp.mkdir(parents=True, exist_ok=True)
        self.dir = tempfile.TemporaryDirectory(dir=tmp)
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / 'outbox.sqlite'
        self.box = Outbox(self.path)
        self.client = NativeRoomClient({'platform':'ordinary','userid':123,'token':'test-only-token','mid':'a'*32})
        self.member = {'userid':123,'role':2,'nickname':'Whale','img':'','vip_type':0}
    def test_build_only_own_identity_and_valid_session(self):
        body = message_body(self.client,456,'789',self.member,'hello')
        self.assertEqual(body['message']['msgtype'],801)
        self.assertEqual(body['message']['alert'],'hello')
        self.assertEqual(body['message']['sysMsg'],0)
        for member in [dict(self.member,userid=789),dict(self.member,role=1),dict(self.member,vip_type=-1)]:
            with self.assertRaises(RoomError): message_body(self.client,456,'789',member,'hello')
    def test_replies_are_single_attempt_across_restart(self):
        calls=[]
        def send(text): calls.append(text);return {'status':1,'data':{'msgid':'555'}}
        first=self.box.once(456,42,0,'hello',permit=lambda:None,send=send)
        again=Outbox(self.path).once(456,42,0,'hello',permit=lambda:None,send=send)
        self.assertEqual(first['state'],'accepted')
        self.assertTrue(again['duplicate'])
        self.assertEqual(calls,['hello'])
        self.assertNotIn(b'hello',self.path.read_bytes())
    def test_unknown_result_or_crash_does_not_resend(self):
        calls=[]
        def send(_): calls.append(1);raise OSError('lost response')
        self.assertEqual(self.box.once(456,42,0,'hello',permit=lambda:None,send=send)['state'],'uncertain')
        self.assertEqual(self.box.once(456,42,0,'hello',permit=lambda:None,send=send)['state'],'uncertain')
        self.assertEqual(len(calls),1)
    def test_explicit_rejection_is_preserved(self):
        result=self.box.once(456,42,0,'hello',permit=lambda:None,send=lambda _: {'status':0,'errcode':20001})
        self.assertEqual(result['state'],'rejected')
    def test_pause_rejects_before_any_send_or_reservation(self):
        def denied(): raise RoomError('paused')
        with self.assertRaises(RoomError): self.box.once(456,42,0,'hello',permit=denied,send=lambda _: self.fail('sent'))
        result=self.box.once(456,42,0,'hello',permit=lambda:None,send=lambda _: {'status':1,'data':{'msgid':55}})
        self.assertEqual(result['state'],'accepted')
    def test_cannot_change_text_for_same_message_part(self):
        self.box.once(456,42,0,'hello',permit=lambda:None,send=lambda _: {'status':1,'data':{'msgid':55}})
        with self.assertRaises(RoomError): self.box.once(456,42,0,'different',permit=lambda:None,send=lambda _: self.fail('sent'))
    def test_caps_reply_parts_and_text(self):
        for part,text in [(3,'hello'),(-1,'hello'),(0,''),(0,'a'*301)]:
            with self.assertRaises(RoomError):self.box.once(456,42,part,text,permit=lambda:None,send=lambda _: self.fail('sent'))


if __name__ == '__main__':unittest.main()

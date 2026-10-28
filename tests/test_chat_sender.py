from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'room'))
from chat_sender import send_text
from native_room import NativeRoomClient,ENDPOINTS
from ordinary_room import RoomError

class SenderTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def transport(*a):self.calls.append(a);return {'status':1,'data':{'msgid':'1'}}
        self.client=NativeRoomClient({'platform':'ordinary','userid':123,'mid':'a'*32,'token':'test-only-token'},transport=transport)
        self.member={'userid':123,'role':2,'nickname':'Whale','img':''}
    def test_fixed_official_endpoint_and_one_message(self):
        send_text(self.client,456,'789',self.member,'hello')
        self.assertTrue(ENDPOINTS['chat'].endswith('/musicroom/message'))
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][0],'chat')
        self.assertEqual(self.calls[0][2]['message']['alert'],'hello')
    def test_wrong_member_cannot_dispatch(self):
        with self.assertRaises(RoomError):send_text(self.client,456,'789',dict(self.member,userid=999),'hello')
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()

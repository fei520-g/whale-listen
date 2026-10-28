import io
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs,urlsplit
from urllib.error import URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'room'))
from history_client import read_room_history,read_room_newest
from native_room import NativeRoomClient
from ordinary_room import RoomError


class Response:
    def __init__(self,data,headers=None):self.buf=io.BytesIO(data);self.headers=headers or {}
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self,n):return self.buf.read(n)
class Opener:
    def __init__(self,response):self.response=response;self.requests=[]
    def open(self,req,timeout):
        self.requests.append(req)
        if isinstance(self.response,Exception):raise self.response
        return self.response


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.client=NativeRoomClient({'platform':'ordinary','userid':123,'token':'secret-test-token','mid':'a'*32},clock=lambda:1000)
    def opener(self,body,headers=None):return Opener(Response(json.dumps(body).encode(),headers))
    def test_only_fixed_tls_gateway_and_exact_room_tag(self):
        op=self.opener({'status':1,'errcode':0,'list':[]})
        self.assertEqual(read_room_history(self.client,456,limit=3,opener=op)['list'],[])
        url=urlsplit(op.requests[0].full_url)
        self.assertEqual((url.scheme,url.hostname,url.path),('https','gateway.kugou.com','/msg.mobile/v3/msgtag/history'))
        q=parse_qs(url.query)
        self.assertEqual(q['tag'],['genting:456'])
        self.assertEqual(q['pagesize'],['3'])
        self.assertIn('signature',q)
    def test_bad_room_and_limit_rejected_before_network(self):
        op=self.opener({'status':1,'list':[]})
        for room,limit in [('abc',3),(456,0),(456,50),(456,True)]:
            with self.assertRaises(RoomError):read_room_history(self.client,room,limit=limit,opener=op)
        self.assertEqual(op.requests,[])
    def test_security_challenge_stops(self):
        op=self.opener({'status':1,'list':[]},{'ssa-code':'required'})
        with self.assertRaises(RoomError):read_room_history(self.client,456,opener=op)
        self.assertEqual(len(op.requests),1)
    def test_newest_uses_same_fixed_gateway_and_valid_cursor(self):
        op=self.opener({'status':1,'list':[]})
        read_room_newest(self.client,456,'99',limit=3,opener=op)
        u=urlsplit(op.requests[0].full_url)
        self.assertEqual(u.path,'/msg.mobile/v3/msgtag/newest')
        self.assertEqual(parse_qs(u.query)['minid'],['99'])
        with self.assertRaises(RoomError):read_room_newest(self.client,456,'bad',opener=op)
        with self.assertRaises(RoomError):read_room_newest(self.client,456,None,opener=op)
        self.assertEqual(len(op.requests),1)
    def test_malformed_and_oversize_fail_closed(self):
        for response in [Response(b'not json'),Response(b'x'*(128*1024+1)),
                         Response(b'{"status":0,"errcode":20001}'),Response(b'{"status":1,"list":{}}')]:
            with self.subTest(response=response),self.assertRaises(RoomError):read_room_history(self.client,456,opener=Opener(response))
    def test_network_error_is_redacted_and_not_retried(self):
        op=Opener(URLError('secret-test-token'))
        with self.assertRaises(RoomError) as err:read_room_history(self.client,456,opener=op)
        self.assertNotIn('secret-test-token',str(err.exception))
        self.assertEqual(len(op.requests),1)


if __name__=='__main__':unittest.main()

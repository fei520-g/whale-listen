import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'room'))
from worker_client import WorkerClient
from ordinary_room import RoomError

PROGRAM='''import sys,json
for line in sys.stdin:
 r=json.loads(line)
 if r['action']=='start':out={'ok':True,'state':'ready'}
 elif r['action']=='reply':out={'ok':True,'messages':['hello']}
 elif r['action']=='stop':out={'ok':True,'state':'stopped'}
 else:out={'ok':False}
 print(json.dumps(out),flush=True)
 if r['action']=='stop':break
'''

class WorkerTests(unittest.TestCase):
    def test_start_reply_and_stop_with_fake_child(self):
        w=WorkerClient([sys.executable,'-u','-c',PROGRAM],env=dict(os.environ),timeout=5)
        try:self.assertEqual(w.complete('test'),['hello'])
        finally:w.close()
        self.assertIsNotNone(w.proc.poll())
    def test_disconnect_does_not_retry(self):
        program="import sys,json;print(json.dumps({'ok':True}),flush=True);sys.stdin.readline()"
        w=WorkerClient([sys.executable,'-u','-c',program],env=dict(os.environ),timeout=5)
        with self.assertRaises(RoomError):w.complete('test')
        self.assertTrue(w.closed)
        with self.assertRaises(RoomError):w.complete('second')

if __name__=='__main__':unittest.main()

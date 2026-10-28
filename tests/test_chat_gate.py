from pathlib import Path
import sys
import tempfile
import sqlite3
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'room'))
from chat_gate import ChatGate
from ordinary_room import RoomError

MEMBERS = [{'userid': 789, 'role': 1}, {'userid': 123, 'role': 2}]
def row(mid, uid=789, stamp=1001, tag='genting:456', kind=801, text='你好呀', sysmsg=0):
    return {'msgid': str(mid), 'uid': uid, 'addtime': stamp, 'tag': tag,
            'message': {'msgtype': kind, 'alert': text, 'sysMsg': sysmsg}}


class GateTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(__file__).resolve().parents[1] / 'testing' / 'tmp'
        tmp.mkdir(parents=True, exist_ok=True)
        self.dir = tempfile.TemporaryDirectory(dir=tmp)
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / 'gate.sqlite'
        self.now = 1000
        self.gate = ChatGate(self.path, clock=lambda: self.now)
        self.gate.begin('456')
        self.now = 1002
    def poll(self, rows, members=MEMBERS):
        return self.gate.ingest('456', 789, 123, members, {'status': 1, 'errcode': 0, 'list': rows})
    def test_baseline_then_only_new_owner_text_once(self):
        self.assertEqual(self.poll([row(1)]), [])
        self.assertEqual([x['text'] for x in self.poll([row(2), row(1)])], ['你好呀'])
        self.assertEqual(self.poll([row(1), row(2)]), [])
        self.assertNotIn('你好呀'.encode(), self.path.read_bytes())
    def test_own_message_system_or_old_message_do_not_trigger(self):
        self.poll([])
        self.assertEqual(self.poll([row(1,uid=123), row(2,kind=500), row(3,sysmsg=1), row(4,stamp=999)]), [])
    def test_other_participants_pause_before_recording(self):
        self.poll([])
        with self.assertRaises(RoomError): self.poll([row(2)], MEMBERS + [{'userid': 777, 'role': 2}])
        self.assertEqual(len(self.poll([row(2)])), 1)
    def test_wrong_tag_rolls_back_batch(self):
        self.poll([])
        with self.assertRaises(RoomError): self.poll([row(1), row(2,tag='genting:999')])
        self.assertEqual(len(self.poll([row(1)])), 1)
    def test_too_many_or_bad_records_fail_closed(self):
        self.poll([])
        with self.assertRaises(RoomError): self.poll([row(i+1) for i in range(49)])
        with self.assertRaises(RoomError): self.poll([row('abc')])
    def test_same_room_restart_uses_new_baseline(self):
        self.poll([])
        self.assertEqual(len(self.poll([row(1)])),1)
        self.gate.begin('456')
        self.assertEqual(self.poll([row(1),row(2)]),[])
        self.assertEqual(len(self.poll([row(1),row(2),row(3,stamp=1002)])),1)
    def test_unbound_room_fails(self):
        with self.assertRaises(RoomError):
            self.gate.ingest('457',789,123,MEMBERS,{'status':1,'errcode':0,'list':[]})
    def test_malformed_author_and_empty_or_future_text_never_forwarded(self):
        self.poll([])
        self.assertEqual(self.poll([row(1,uid='bad'),row(2,text='  '),row(3,stamp=2000)]),[])
    def test_result_sorted_by_time_and_id(self):
        self.poll([])
        out=self.poll([row(5,stamp=1002,text='b'),row(2,stamp=1001,text='a')])
        self.assertEqual([x['text'] for x in out],['a','b'])
    def test_full_baseline_then_incremental_cursor(self):
        self.assertEqual(self.poll([row(i+1) for i in range(49)]),[])
        self.assertEqual(self.gate.cursor('456'),'49')
        data={'status':1,'errcode':0,'list':[row(50)]}
        result=self.gate.ingest('456',789,123,MEMBERS,data,newest=True)
        self.assertEqual(len(result),1);self.assertEqual(self.gate.cursor('456'),'50')
        self.assertEqual(self.gate.ingest('456',789,123,MEMBERS,{'status':1,'errcode':0,'list':[]},newest=True),[])
    def test_newest_wrong_cursor_fails_without_advancing(self):
        self.poll([row(5)])
        with self.assertRaises(RoomError):self.gate.ingest('456',789,123,MEMBERS,{'status':1,'errcode':0,'list':[row(5)]},newest=True)
        self.assertEqual(self.gate.cursor('456'),'5')
    def test_previous_database_schema_migrates(self):
        old=Path(self.dir.name)/'old.sqlite'
        db=sqlite3.connect(old)
        try:db.execute('CREATE TABLE session(id INTEGER PRIMARY KEY, room_hash TEXT NOT NULL, start_sec INTEGER NOT NULL, baseline INTEGER NOT NULL)');db.commit()
        finally:db.close()
        migrated=ChatGate(old,clock=lambda:1000);migrated.begin('456');self.assertIsNone(migrated.cursor('456'))


if __name__ == '__main__': unittest.main()

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'room'))
from control import Store, Superseded, ack, leave_known
from ordinary_room import RoomError
from room_daemon import Supervisor

LINK = 'https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code=' + 'b' * 32
PUBLIC = {'roomid': '456', 'members': 2, 'member_data': [
    {'userid': 789, 'role': 1}, {'userid': 123, 'role': 2}]}


class Client:
    userid = 123
    def __init__(self):
        self.online, self.calls, self.unknown_join, self.unknown_leave = False, [], False, False
    def status(self, room):
        self.calls.append('status')
        return {'status': 1, 'data': {'status': 1, 'me_online': int(self.online), 'eid': '999'}}
    def join(self, *a, **kw):
        self.calls.append('join')
        self.online = True
        if self.unknown_join:
            raise RoomError('network', retryable=True)
        return {'status': 1, 'data': {}}
    def heartbeat(self, *a, **kw):
        self.calls.append('heartbeat')
        return {'status': 1, 'data': {}}
    def leave(self, *a, **kw):
        self.calls.append('leave')
        self.online = False
        if self.unknown_leave:
            raise RoomError('network', retryable=True)
        return {'status': 1, 'errcode': 0}  # No data field.


class ControlTests(unittest.TestCase):
    def setUp(self):
        testing = Path(__file__).resolve().parents[1] / 'testing' / 'tmp'
        testing.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=testing)
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'room.sqlite')
        self.client = Client()
        self.supervisor = Supervisor(self.store, self.client, lambda _: PUBLIC,
                                    hashlib.sha256(b'789').hexdigest())
        self.counter = 0
    def command(self, action, **extra):
        self.counter += 1
        req = dict(version=1, action=action, request_id=f'command-{self.counter:016}',
                   expected_revision=self.store.read()['revision'], **extra)
        return self.supervisor.control(req)
    def join(self):
        self.command('join', invite=LINK)
        self.supervisor.step()
    def test_idle_and_restart_do_not_join(self):
        self.supervisor.step()
        self.store.recover()
        self.supervisor.step()
        self.assertEqual(self.client.calls, [])
    def test_leave_is_durable_and_works_with_no_invite(self):
        self.join()
        response = self.command('leave')
        self.assertFalse(response['present'])
        self.assertFalse(response['leave_confirmed'])
        self.assertIsNone(self.store.read()['link'])
        self.supervisor.reader = lambda _: self.fail('must not resolve invite to leave')
        self.supervisor.step()
        self.assertTrue(self.store.public()['leave_confirmed'])
        self.assertEqual(self.client.calls.count('leave'), 1)
        self.store.recover()
        self.supervisor.step()
        self.assertEqual(self.client.calls.count('join'), 1)
    def test_unknown_leave_response_checked_without_resend(self):
        self.join()
        self.client.unknown_leave = True
        self.command('leave')
        self.supervisor.step()
        self.supervisor.step()
        self.assertTrue(self.store.public()['leave_confirmed'])
        self.assertEqual(self.client.calls.count('leave'), 1)
    def test_restart_online_only_leaves(self):
        self.join()
        self.store.recover()
        self.supervisor.step()
        self.assertEqual(self.client.calls.count('join'), 1)
        self.assertEqual(self.client.calls.count('leave'), 1)
    def test_expired_session_is_idempotently_left(self):
        self.client.status = lambda _: {'status': 0, 'errcode': 20004}
        self.assertTrue(leave_known(self.client, '456')['confirmed'])
        self.assertNotIn('leave', self.client.calls)
    def test_auth_error_is_not_departure_confirmation(self):
        self.client.status = lambda _: {'status': 0, 'errcode': 20001}
        with self.assertRaises(RoomError): leave_known(self.client, '456')
    def test_unknown_join_not_sent_twice_even_after_pause(self):
        self.client.unknown_join = True
        self.command('join', invite=LINK)
        self.supervisor.step()
        self.command('pause')
        self.supervisor.step()
        self.assertEqual(self.client.calls.count('join'), 1)
        self.assertEqual(self.store.public()['state'], 'online')
    def test_wrong_owner_blocks_all_native_calls(self):
        self.supervisor.owner = hashlib.sha256(b'999').hexdigest()
        self.command('join', invite=LINK)
        self.supervisor.step()
        self.assertEqual(self.client.calls, [])
        self.assertFalse(self.store.public()['present'])
    def test_old_request_cannot_rejoin_after_leave(self):
        old = dict(version=1, action='join', request_id='x' * 20, expected_revision=0, invite=LINK)
        self.store.command(old)
        self.command('leave')
        result = self.store.command(old)
        self.assertTrue(result['duplicate'])
        self.assertFalse(result['present'])
        with self.assertRaises(RoomError): self.store.command(dict(old, request_id='y' * 20))
    def test_only_fixed_actions_and_no_private_fields(self):
        for req in [{'version': True, 'action': 'status'}, {'version': 1, 'action': []},
                    {'version': 1, 'action': 'status', 'command': 'id'},
                    {'version': 1, 'action': 'chat'}]:
            with self.assertRaises(RoomError): self.store.command(req)
        self.command('join', invite=LINK)
        data = json.dumps(self.store.public())
        self.assertNotIn('b' * 32, data)
        self.assertNotIn('roomid', data)
    def test_chat_cannot_enable_before_capability_is_proven(self):
        self.join()
        with self.assertRaises(RoomError):self.command('chat')
        self.assertEqual(self.store.public()['reply_mode'],'paused')
    def test_ack_without_data_and_rejected_ack(self):
        ack({'status': 1, 'errcode': 0})
        with self.assertRaises(RoomError): ack({'status': 0, 'data': {}})
    def test_leave_cancels_tick_during_public_read(self):
        def reader(_):
            self.command('leave')
            return PUBLIC
        self.supervisor.reader = reader
        self.command('join', invite=LINK)
        try: self.supervisor.step()
        except Superseded: pass
        self.assertEqual(self.client.calls, [])
        self.assertFalse(self.store.public()['present'])
    def test_new_invite_replaces_old_engine_after_leave_before_first_bind(self):
        new_link = LINK.replace('b' * 32, 'c' * 32)
        reads = []
        def reader(link):
            reads.append(link)
            if len(reads) == 1:
                self.command('leave')
                self.command('join', invite=new_link)
            return PUBLIC
        self.supervisor.reader = reader
        self.command('join', invite=LINK)
        self.supervisor.step()
        self.supervisor.step()
        self.assertEqual(reads, [LINK, new_link, new_link])
        self.assertEqual(self.client.calls.count('join'), 1)
        self.assertEqual(self.store.public()['state'], 'online')
    def test_no_quit_retry_after_unknown_and_restart(self):
        self.join()
        self.client.leave = lambda *a, **kw: (_ for _ in ()).throw(RoomError('unknown'))
        self.command('leave')
        self.supervisor.step()
        self.assertEqual(self.store.public()['state'], 'leave_unconfirmed')
        self.store.recover()
        self.client.leave = lambda *a, **kw: self.fail('must not retry quit')
        self.supervisor.step()
        self.assertFalse(self.store.public()['leave_confirmed'])


if __name__ == '__main__': unittest.main()

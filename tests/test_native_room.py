import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'room'))
import native_room as m

CREDS = {'platform': 'ordinary', 'userid': '123', 'token': 'test-private-token', 'mid': 'a' * 32}


class NativeRoomTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def transport(*args):
            self.calls.append(args)
            return {'status': 1, 'errcode': 0, 'data': {}}
        self.client = m.NativeRoomClient(CREDS, transport=transport, clock=lambda: 1000)

    def test_status_does_not_join_or_put_credentials_in_query(self):
        self.client.status('456')
        op, params, body = self.calls[0]
        self.assertEqual(op, 'status')
        self.assertNotIn('token', params)
        self.assertNotIn('userid', params)
        self.assertEqual(body, {'userid': 123, 'token': CREDS['token'], 'roomid': 456, 'req': 1})

    def test_join_requires_consent_before_network(self):
        with self.assertRaises(m.RoomError):
            self.client.join('456', 'b' * 32, consent=False, creator='789')
        self.assertEqual(self.calls, [])

    def test_join_is_one_request_and_has_no_playback_or_chat_fields(self):
        self.client.join('456', 'b' * 32, consent=True, creator='789')
        op, _, body = self.calls[0]
        self.assertEqual(op, 'join')
        self.assertEqual(set(body), {'userid', 'token', 'roomid', 'creator', 'enter_frm', 'code', 'supports'})
        self.assertEqual(len(self.calls), 1)

    def test_same_account_as_inviter_blocked(self):
        with self.assertRaises(m.RoomError):
            self.client.join('456', 'b' * 32, consent=True, creator='123')
        self.assertEqual(self.calls, [])

    def test_invalid_ids_and_code_fail_closed(self):
        for room in [None, -2, 'abc', '123/../foo', '1' * 30]:
            with self.subTest(room=room), self.assertRaises(m.RoomError):
                self.client.status(room)
        for code in ['x', 'x' * 32, None]:
            with self.subTest(code=code), self.assertRaises(m.RoomError):
                self.client.join('456', code, consent=True, creator='789')
        self.assertEqual(self.calls, [])

    def test_concept_account_and_bad_credentials_rejected(self):
        for changes in [{'platform': 'lite'}, {'token': ''}, {'mid': 'bad'}, {'userid': None}]:
            with self.subTest(changes=changes), self.assertRaises(m.RoomError):
                m.NativeRoomClient(dict(CREDS, **changes))

    def test_no_arbitrary_native_endpoint(self):
        with self.assertRaises(m.RoomError):
            m.request_native_json('send-message', {}, {})

    def test_summary_has_no_account_identifiers_or_arbitrary_messages(self):
        safe = m.summary({'status': 0, 'errcode': 20001, 'error': CREDS['token'],
                          'data': {'token': CREDS['token'], 'userid': 123, 'roomid': 456,
                                   'me_online': 0}})
        self.assertNotIn(CREDS['token'], str(safe))
        self.assertNotIn(123, safe.values())
        self.assertNotIn(456, safe.values())
        self.assertEqual(safe['me_online'], 0)

    def test_body_is_signed_exactly(self):
        params = {'mid': 'test', 'clienttime': 1000}
        body = '{"token":"test-only"}'
        expected = hashlib.md5((m.ANDROID_SALT + 'clienttime=1000mid=test' + body + m.ANDROID_SALT).encode()).hexdigest()
        self.assertEqual(m.sign_android(params, body), expected)
        self.assertNotEqual(m.sign_android(params, body + ' '), expected)

    def test_leave_cannot_close_room_and_requires_consent(self):
        with self.assertRaises(m.RoomError):
            self.client.leave('456', consent=False)
        self.assertEqual(self.calls, [])
        self.client.leave('456', consent=True)
        self.assertEqual(self.calls[0][0], 'leave')
        self.assertTrue(m.ENDPOINTS['leave'].endswith('/quit'))
        self.assertNotIn('/close', m.ENDPOINTS.values())

    def test_heartbeat_only_reports_room_presence(self):
        self.client.heartbeat('456', '987654321')
        op, _, body = self.calls[0]
        self.assertEqual(op, 'heartbeat')
        self.assertEqual(body, {'userid': 123, 'token': CREDS['token'],
                                'roomid': 456, 'eid': '987654321', 'event': 1})
        self.assertTrue(m.ENDPOINTS['heartbeat'].endswith('/member/rpt'))

    def test_heartbeat_requires_valid_session(self):
        for eid in ['', None, 'invalid', '1' * 33]:
            with self.subTest(eid=eid), self.assertRaises(m.RoomError):
                self.client.heartbeat('456', eid)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()

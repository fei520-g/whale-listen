import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'room' / 'ordinary_room.py'
spec = importlib.util.spec_from_file_location('ordinary_room', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

LINK = 'https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code=' + 'a' * 32 + '&eid=987654'
MID = '1' * 32


class RoomTests(unittest.TestCase):
    def client(self, response):
        self.calls = []
        def transport(op, params):
            self.calls.append((op, params))
            return response
        return m.OrdinaryRoomProbe(MID, transport=transport, clock=lambda: 1000)

    def test_invite_uses_code_not_eid(self):
        c = self.client({'status': 1, 'errcode': 0, 'data': {'roomid': 123, 'members': [{}]}})
        self.assertEqual(c.inspect(LINK)['roomid'], '123')
        self.assertEqual(self.calls[0][1]['code'], 'a' * 32)
        self.assertNotIn('eid', self.calls[0][1])

    def test_host_path_and_duplicate_code_validation(self):
        for link in [LINK.replace('h5.kugou.com', 'h5.kugou.com.evil.test'),
                     LINK.replace('https:', 'http:'), LINK + '&code=' + 'b' * 32,
                     LINK.replace('/sharepage/', '/other/'), LINK.replace('h5.kugou.com', 'user@h5.kugou.com'),
                     LINK.replace('a' * 32, 'x')]:
            with self.subTest(link=link), self.assertRaises(m.RoomError):
                m.invite_code(link)

    def test_invalid_invite_never_hits_network(self):
        c = self.client({})
        with self.assertRaises(m.RoomError):
            c.inspect('https://example.com/')
        self.assertEqual(self.calls, [])

    def test_signing_is_order_independent_and_body_bound(self):
        a = m.sign_web({'b': 2, 'a': 1})
        self.assertEqual(a, m.sign_web({'a': 1, 'b': 2}))
        self.assertNotEqual(a, m.sign_web({'a': 1, 'b': 2}, '{}'))
        with self.assertRaises(m.RoomError):
            m.sign_web({'signature': a})

    def test_missing_roomid_never_falls_back_to_eid(self):
        c = self.client({'status': 1, 'data': {'members': []}})
        with self.assertRaises(m.RoomError):
            c.inspect(LINK)

    def test_server_error_is_redacted(self):
        with self.assertRaises(m.RoomError) as caught:
            m.require_success({'status': 0, 'errcode': 403, 'error': 'SECRET_VALUE'})
        self.assertNotIn('SECRET_VALUE', str(caught.exception))

    def test_unknown_operations_and_redirects_rejected(self):
        with self.assertRaises(m.RoomError):
            m.request_json('join', {})
        with self.assertRaises(m.RoomError):
            m.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test')

    def test_challenge_accepts_only_bounded_inline_png(self):
        c = self.client({'status': 1, 'data': {'qrcode': 'x' * 36, 'qrcode_img':
            'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n').decode()}})
        challenge = c.create_challenge()
        self.assertEqual(challenge['key'], 'x' * 36)
        self.assertEqual(self.calls[0][0], 'qr_create')

    def test_remote_qr_image_is_never_fetched(self):
        c = self.client({'status': 1, 'data': {'qrcode': 'x' * 36,
                                             'qrcode_img': 'https://evil.test/qr.png'}})
        with self.assertRaises(m.RoomError):
            c.create_challenge()
        self.assertEqual(len(self.calls), 1)

    def test_authorization_requires_consent_before_network(self):
        c = self.client({})
        with self.assertRaises(m.RoomError):
            c.check_authorization({'key': 'x' * 36, 'created_at': 999}, consent=False)
        self.assertEqual(self.calls, [])

    def test_expired_challenge_never_checks_account(self):
        c = self.client({})
        for timestamp in [700, 1001]:
            with self.assertRaises(m.RoomError):
                c.check_authorization({'key': 'x' * 36, 'created_at': timestamp}, consent=True)
        self.assertEqual(self.calls, [])

    def test_waiting_and_confirm_states(self):
        for state, expected in [(0, 'expired'), (1, 'waiting_scan'), (2, 'waiting_confirm')]:
            c = self.client({'status': 1, 'data': {'status': state}})
            self.assertEqual(c.check_authorization({'key': 'x' * 36, 'created_at': 999}, consent=True),
                             {'state': expected})

    def test_authorized_credentials_remain_explicit_private_data(self):
        c = self.client({'status': 1, 'data': {'status': 4, 'userid': 123, 'token': 'test-private-token'}})
        r = c.check_authorization({'key': 'x' * 36, 'created_at': 999}, consent=True)
        self.assertEqual(r['credentials']['platform'], 'ordinary')
        self.assertNotIn('token', {k: v for k, v in r.items() if k != 'credentials'})

    def test_mistaken_host_account_is_rejected_before_saving(self):
        c = self.client({'status': 1, 'data': {'status': 4, 'userid': 123, 'token': 'test-private-token'}})
        challenge = {'key': 'x' * 36, 'created_at': 999,
                     'excluded_userid_hash': hashlib.sha256(b'123').hexdigest()}
        with self.assertRaises(m.RoomError):
            c.check_authorization(challenge, consent=True)
        challenge['excluded_userid_hash'] = hashlib.sha256(b'456').hexdigest()
        self.assertEqual(c.check_authorization(challenge, consent=True)['state'], 'authorized')

    def test_broken_account_constraint_fails_closed(self):
        c = self.client({'status': 1, 'data': {'status': 4, 'userid': 123, 'token': 'test-private-token'}})
        with self.assertRaises(m.RoomError):
            c.check_authorization({'key': 'x' * 36, 'created_at': 999,
                                   'excluded_userid_hash': 'bad'}, consent=True)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI integration')
    def test_windows_dpapi_encrypts_without_plaintext(self):
        data = {'token': 'unit-test-sensitive-credential', 'platform': 'ordinary'}
        encrypted = m.protect_credentials(data)
        self.assertTrue(encrypted.startswith(b'WMKG1\n'))
        self.assertNotIn(b'unit-test-sensitive-credential', encrypted)
        self.assertEqual(m.unprotect_credentials(encrypted), data)

    def test_plaintext_credentials_rejected(self):
        with self.assertRaises(m.RoomError):
            m.unprotect_credentials(b'{"token":"not-an-encrypted-file"}')


if __name__ == '__main__':
    unittest.main()

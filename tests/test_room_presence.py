from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'room'))
from ordinary_room import RoomError
from room_presence import Presence, RoomEnded

LINK = 'https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code=' + 'b' * 32


class FakeClient:
    userid = 123
    def __init__(self, statuses=None):
        self.statuses = statuses or [1]
        self.joins = self.beats = self.reads = 0
        self.interval = 30
        self.beat_response = {'status': 1, 'data': {}}
    def status(self, room):
        self.reads += 1
        online = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {'status': 1, 'data': {'status': 1, 'me_online': online,
                'eid': '987654321', 'hbt_intval': self.interval}}
    def join(self, *_, **__):
        self.joins += 1
        return {'status': 1, 'data': {}}
    def heartbeat(self, *_, **__):
        self.beats += 1
        return self.beat_response


class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.public = {'roomid': '456', 'members': 2,
                       'member_data': [{'userid': 789, 'role': 1}, {'userid': 123, 'role': 2}],
                       'song_info': {'name': 'Test song', 'singer': 'Test artist'}}
        self.engine = Presence(self.client, lambda _: self.public, LINK, clock=lambda: 1000)

    def test_online_account_is_not_joined_again(self):
        state, interval = self.engine.tick()
        self.assertEqual(state['state'], 'online')
        self.assertEqual(self.client.joins, 0)
        self.assertEqual(self.client.beats, 1)
        self.assertEqual(interval, 30)
        self.assertFalse(state['audio_rendered'])
        self.assertTrue(state['metadata_only'])
        self.assertNotIn('token', state)

    def test_startup_join_is_confirmed_by_status(self):
        self.client.statuses = [0, 1]
        self.engine.tick()
        self.assertEqual(self.client.joins, 1)
        self.assertEqual(self.client.reads, 2)

    def test_failed_join_confirmation_never_reports_online(self):
        self.client.statuses = [0]
        with self.assertRaises(RoomEnded):
            self.engine.tick()
        self.assertEqual(self.client.beats, 0)
        with self.assertRaises(RoomEnded):
            self.engine.tick()
        self.assertEqual(self.client.joins, 1)

    def test_leaving_after_online_does_not_force_rejoin(self):
        self.engine.tick()
        self.client.statuses = [0]
        with self.assertRaises(RoomEnded):
            self.engine.tick()
        self.assertEqual(self.client.joins, 0)

    def test_changed_room_is_not_joined(self):
        self.engine.tick()
        self.public['roomid'] = '999'
        with self.assertRaises(RoomEnded):
            self.engine.tick()
        self.assertEqual(self.client.joins, 0)
        self.assertEqual(self.client.beats, 1)

    def test_own_host_account_is_rejected_before_native_calls(self):
        self.public['member_data'][0]['userid'] = 123
        with self.assertRaises(RoomEnded):
            self.engine.tick()
        self.assertEqual(self.client.reads, 0)

    def test_missing_participant_is_not_reported_online(self):
        self.public['member_data'] = [{'userid': 789, 'role': 1}]
        with self.assertRaises(RoomEnded):
            self.engine.tick()

    def test_rejected_heartbeat_is_failure(self):
        self.client.beat_response = {'status': 0, 'errcode': 20004}
        with self.assertRaises(RoomError):
            self.engine.tick()

    def test_poll_interval_cannot_spin_or_sleep_unbounded(self):
        for value, expected in [(0, 15), (100000, 60), (None, 30)]:
            self.client.interval = value
            self.assertEqual(self.engine.tick()[1], expected)


if __name__ == '__main__':
    unittest.main()

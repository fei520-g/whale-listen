"""Independent official-room presence worker. No incoming ports or AI calls."""
import argparse
import json
import os
from pathlib import Path
import signal
import stat
import time

from ordinary_room import (OrdinaryRoomProbe, RoomError, invite_code, private_write,
                           request_json, require_success)
from native_room import NativeRoomClient


class RoomEnded(RoomError):
    pass


def public_reader(mid):
    def read(link):
        captured = {}
        def capture(op, params):
            result = request_json(op, params)
            captured.update(require_success(result))
            return result
        result = OrdinaryRoomProbe(mid, transport=capture).inspect(link)
        result['member_data'] = captured.get('members', [])
        result['song_info'] = captured.get('song_info', {})
        return result
    return read


class Presence:
    def __init__(self, client, read_public, link, clock=time.time):
        invite_code(link)
        self.client, self.read_public, self.link, self.clock = client, read_public, link, clock
        self.roomid = None
        self.ever_online = self.join_attempted = False

    def tick(self):
        public = self.read_public(self.link)
        room = public['roomid']
        if self.roomid is not None and self.roomid != room:
            raise RoomEnded('邀请的房间发生变化，已停止')
        self.roomid = room
        owners = [m for m in public.get('member_data', [])
                  if isinstance(m, dict) and m.get('role') == 1]
        if len(owners) != 1 or str(owners[0].get('userid')) == str(self.client.userid):
            raise RoomEnded('无法确认独立的房主账号，已停止')
        status = require_success(self.client.status(room))
        if status.get('status') != 1:
            raise RoomEnded('房间已结束，已停止')
        if status.get('me_online') != 1:
            if self.ever_online or self.join_attempted:
                raise RoomEnded('账号已离开房间，已停止；不会反复重新加入')
            # One startup join only. An ambiguous network failure is checked by
            # status on the next tick, never retried blindly as another join.
            self.join_attempted = True
            require_success(self.client.join(room, invite_code(self.link), consent=True,
                                             creator=owners[0].get('userid')))
            status = require_success(self.client.status(room))
            if status.get('me_online') != 1:
                raise RoomEnded('入房结果未确认，已停止')
            public = self.read_public(self.link)
        require_success(self.client.heartbeat(room, str(status.get('eid', ''))))
        visible = any(str(m.get('userid')) == str(self.client.userid)
                      for m in public.get('member_data', []) if isinstance(m, dict))
        if not visible:
            raise RoomEnded('公开房间成员中未找到测试账号，已停止')
        self.ever_online = True
        song = public.get('song_info') or {}
        song = song if isinstance(song, dict) else {}
        result = {'version': 1, 'source': 'kugou-native-room', 'state': 'online',
                  'observed_at': self.clock(), 'members': public['members'],
                  'participant_visible': True, 'playback_control': False,
                  'audio_rendered': False, 'metadata_only': True}
        # Native room membership does not prove that a model heard any audio.
        result['song'] = {k: song[k][:256] for k in ('name', 'singer') if isinstance(song.get(k), str)}
        interval = status.get('hbt_intval', 30)
        interval = interval if type(interval) is int else 30
        return result, max(15, min(60, interval))


def read_private(path):
    if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RoomError('凭证或邀请文件权限过宽，拒绝启动')
    return path.read_text(encoding='utf8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--invite', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    client = NativeRoomClient(json.loads(read_private(args.credentials)))
    engine = Presence(client, public_reader(client.mid), read_private(args.invite).strip())
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    failures = 0
    while not stopped:
        try:
            result, delay = engine.tick()
            failures = 0
        except RoomError as exc:
            failures += 1
            retrying = exc.retryable and failures < 3 and not isinstance(exc, RoomEnded)
            result = {'version': 1, 'source': 'kugou-native-room',
                      'state': 'retrying' if retrying else 'closed',
                      'observed_at': time.time(), 'error': str(exc)}
            delay = min(60, 30 * 2 ** (failures - 1))
            if not retrying:
                stopped = True
        private_write(args.state, json.dumps(result, ensure_ascii=False, indent=2).encode('utf8'))
        print(json.dumps({k: result.get(k) for k in ('state', 'members', 'error')}, ensure_ascii=False), flush=True)
        if args.once or stopped:
            return 0 if result['state'] == 'online' else 1
        # Short waits make systemd stop responsive; no unbounded shutdown wait.
        deadline = time.monotonic() + delay
        while not stopped and time.monotonic() < deadline:
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    private_write(args.state, json.dumps({'version': 1, 'state': 'stopped',
                                          'observed_at': time.time()}).encode())
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RoomError, ValueError, OSError):
        print('Room worker cannot start; check private configuration and permissions.', flush=True)
        raise SystemExit(1) from None

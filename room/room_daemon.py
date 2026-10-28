"""Room supervisor, idle until explicit join. Private Unix socket, no TCP/AI.

The dispatch lock serializes API calls with intent commits. Once a leave intent
is accepted, an old tick cannot dispatch another join or heartbeat.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socketserver
import threading

from control import Store, Superseded, leave_known
from native_room import NativeRoomClient
from ordinary_room import RoomError
from room_presence import Presence, public_reader, read_private


class Supervisor:
    def __init__(self, store, client, read_public, owner_sha256):
        if len(owner_sha256) != 64 or any(c not in '0123456789abcdef' for c in owner_sha256):
            raise RoomError('需要绑定已确认的房主账号')
        self.store, self.client, self.reader, self.owner = store, client, read_public, owner_sha256
        self.dispatch = threading.RLock()
        self.wake = threading.Event()
        self.engine, self.generation, self.join_generation = None, None, None
        self.failures = 0

    def control(self, request):
        # May wait for one bounded network operation. This is an intent receipt,
        # not proof of remote departure: leave_confirmed is returned separately.
        with self.dispatch:
            result = self.store.command(request)
        self.wake.set()
        return result

    def guard(self, revision):
        state = self.store.read()
        if state['revision'] != revision or not state['present']:
            raise Superseded('已取消本轮房间操作')

    def make_engine(self, state):
        revision, parent = state['revision'], self
        class GuardedClient:
            userid = parent.client.userid
            def call(self, name, *args, **kwargs):
                with parent.dispatch:
                    parent.guard(revision)
                    return getattr(parent.client, name)(*args, **kwargs)
            def status(self, *a, **kw): return self.call('status', *a, **kw)
            def join(self, *a, **kw): return self.call('join', *a, **kw)
            def heartbeat(self, *a, **kw): return self.call('heartbeat', *a, **kw)
        def read(link):
            self.guard(revision)
            public = self.reader(link)
            owners = [m for m in public.get('member_data', []) if isinstance(m, dict) and m.get('role') == 1]
            if len(owners) != 1 or hashlib.sha256(str(owners[0].get('userid')).encode()).hexdigest() != self.owner:
                raise RoomError('邀请房主与绑定账号不符，未加入')
            self.store.update(revision, room=public['roomid'])
            return public
        return Presence(GuardedClient(), read, state['link'])

    def step(self):
        state = self.store.read()
        revision = state['revision']
        if not state['present']:
            self.engine, self.generation, self.join_generation = None, None, None
            if not state['room']:
                return 30
            try:
                result = leave_known(self.client, state['room'],
                    allow_quit=not state['quit_attempted'],
                    before_quit=lambda: self.store.update(revision, quit_attempted=True))
                self.store.update(revision,
                    room=None if result['confirmed'] else state['room'],
                    state='left' if result['confirmed'] else 'leave_unconfirmed',
                    leave_confirmed=result['confirmed'],
                    error=None if result['confirmed'] else '退出尚未确认；已停止心跳和自动回复')
            except Superseded:
                return 0
            except RoomError:
                self.store.update(revision, state='leave_unconfirmed', leave_confirmed=False,
                                  error='暂时无法核实退出；已停止心跳和自动回复')
            return 30
        if self.generation != revision:
            replacement = self.make_engine(state)
            if self.engine is not None and self.join_generation == state['join_revision']:
                # Pause retains the startup join-attempt guard.
                self.engine.client, self.engine.read_public = replacement.client, replacement.read_public
            else:
                self.engine, self.failures = replacement, 0
                self.join_generation = state['join_revision']
            self.generation = revision
        try:
            _, delay = self.engine.tick()
            self.store.update(revision, state='online', error=None)
            self.failures = 0
            return delay
        except Superseded:
            return 0
        except RoomError as exc:
            self.failures += 1
            if exc.retryable and self.failures < 3:
                self.store.update(revision, state='retrying', error='网络暂时不可用；尚未确认在线')
                return 30 * self.failures
            self.store.update(revision, present=False, reply_mode='paused', link=None,
                              state='leaving', error='房间连接停止，请查看状态后重新分享邀请')
            return 0


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(20)
        try:
            raw = self.rfile.readline(4097)
            if len(raw) > 4096 or not raw.endswith(b'\n'):
                raise RoomError('控制请求过大或未结束')
            result = self.server.supervisor.control(json.loads(raw))
        except (RoomError, ValueError, TypeError, OSError):
            result = {'ok': False, 'error': '房间操作未接受，请刷新状态后重试'}
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--owner-hash', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--socket', type=Path, required=True)
    parser.add_argument('--socket-group', help='group permitted to use the limited control socket')
    parser.add_argument('--enable-chat', action='store_true', help='requires reviewed DSH preset and worker')
    parser.add_argument('--node', type=Path)
    parser.add_argument('--agent-worker', type=Path)
    parser.add_argument('--bridge-root', type=Path)
    parser.add_argument('--room-workspace', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.enable_chat and not all(p is not None and p.is_absolute() for p in
                                    (args.node,args.agent_worker,args.bridge_root,args.room_workspace)):
        raise RoomError('聊天组件的独立路径未配置')
    store = Store(args.database,chat_available=args.enable_chat)
    store.recover()
    client = NativeRoomClient(json.loads(read_private(args.credentials)))
    supervisor = Supervisor(store, client, public_reader(client.mid), read_private(args.owner_hash).strip())
    chat_runner=None
    if args.enable_chat:
        from chat_gate import ChatGate
        from chat_outbox import Outbox
        from chat_runner import ChatRunner
        from history_client import read_room_history,read_room_newest
        from worker_client import WorkerClient
        args.room_workspace.mkdir(mode=0o700,parents=True,exist_ok=True)
        env=dict(os.environ,WHALE_BRIDGE_ROOT=str(args.bridge_root),WHALE_ROOM_WORKSPACE=str(args.room_workspace))
        def make_worker():return WorkerClient([str(args.node),str(args.agent_worker)],env=env)
        chat_runner=ChatRunner(supervisor,ChatGate(args.database.parent/'chat-seen.sqlite'),
                               Outbox(args.database.parent/'chat-outbox.sqlite'),read_room_history,make_worker,read_newest=read_room_newest)
    if args.socket.exists():
        raise RoomError('控制套接字已存在；拒绝覆盖')
    with socketserver.ThreadingUnixStreamServer(str(args.socket), ControlHandler) as server:
        server.daemon_threads = True
        server.supervisor = supervisor
        if args.socket_group:
            import grp
            os.chown(args.socket, -1, grp.getgrnam(args.socket_group).gr_gid)
        args.socket.chmod(0o660)
        stop = threading.Event()
        def shutdown(*_):
            stop.set()
            supervisor.wake.set()
            if chat_runner:chat_runner.stop()
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if chat_runner:threading.Thread(target=chat_runner.run,daemon=True).start()
        try:
            while not stop.is_set():
                supervisor.wake.clear()
                try:
                    delay = supervisor.step()
                except Superseded:
                    delay = 0
                supervisor.wake.wait(delay)
            with supervisor.dispatch:
                store.recover()
            supervisor.step()
        finally:
            server.shutdown()
            args.socket.unlink(missing_ok=True)


if __name__ == '__main__':
    main()

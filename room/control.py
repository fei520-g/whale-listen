"""Durable private room intent; contains no account token or shell commands."""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from ordinary_room import RoomError, invite_code


class Superseded(RoomError):
    pass


class Store:
    def __init__(self, path, clock=time.time, *, chat_available=False):
        self.path, self.clock = Path(path), clock
        self.chat_available = chat_available
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, digest TEXT NOT NULL, revision INTEGER NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO state VALUES(1,?)', (json.dumps({
                'revision': 0, 'present': False, 'reply_mode': 'paused', 'link': None,
                'room': None, 'state': 'left', 'leave_confirmed': True, 'quit_attempted': False,
                'join_revision': None,
                'observed_at': self.clock(), 'error': None}),))
        if os.name != 'nt':
            self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.lock, self.connect() as db:
            return json.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])

    def write(self, db, state):
        db.execute('UPDATE state SET value=? WHERE id=1', (json.dumps(state),))

    def update(self, revision, **fields):
        with self.lock, self.connect() as db:
            state = self.read()
            if revision != state['revision']:
                raise Superseded('操作已被新的控制指令取消')
            state.update(fields, observed_at=self.clock())
            self.write(db, state)
            return state

    def recover(self):
        """Restart never constitutes permission to join/reply again."""
        with self.lock, self.connect() as db:
            state = self.read()
            state.update(revision=state['revision'] + 1, present=False, reply_mode='paused',
                         link=None, state='leaving' if state['room'] else 'left',
                         leave_confirmed=not bool(state['room']), error=None,
                         observed_at=self.clock())
            self.write(db, state)

    def command(self, request):
        if not isinstance(request, dict) or type(request.get('version')) is not int or request['version'] != 1:
            raise RoomError('控制协议版本错误')
        action = request.get('action')
        if not isinstance(action, str):
            raise RoomError('房间操作格式错误')
        allowed = {'version', 'action'} if action == 'status' else {
            'version', 'action', 'request_id', 'expected_revision'}
        if action == 'join':
            allowed.add('invite')
        if action not in {'status', 'join', 'leave', 'pause', 'chat'} or set(request) != allowed:
            raise RoomError('不允许的房间控制操作或字段')
        if action == 'status':
            return self.public()
        rid = request['request_id']
        if not isinstance(rid, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', rid):
            raise RoomError('控制请求编号错误')
        if type(request['expected_revision']) is not int:
            raise RoomError('需要当前房间版本')
        if action == 'join':
            if not isinstance(request['invite'], str) or len(request['invite']) > 2048:
                raise RoomError('邀请链接格式错误')
            invite_code(request['invite'])
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with self.lock, self.connect() as db:
            prior = db.execute('SELECT digest,revision FROM commands WHERE id=?', (rid,)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise RoomError('请求编号已被其他操作使用')
                return dict(self.public(), accepted=True, duplicate=True, command_revision=prior[1])
            state = self.read()
            if request['expected_revision'] != state['revision']:
                raise RoomError('状态已经变化，请刷新后再操作')
            if action == 'join' and (state['present'] or state['room']):
                raise RoomError('请先退出当前房间并确认，再分享新邀请')
            if action == 'chat' and (not self.chat_available or not state['present'] or state['state'] != 'online'):
                raise RoomError('房间闲聊尚未就绪')
            state['revision'] += 1
            state.update(error=None, observed_at=self.clock())
            if action == 'join':
                state.update(present=True, reply_mode='paused', link=request['invite'],
                             state='joining', leave_confirmed=False, quit_attempted=False,
                             join_revision=state['revision'])
            elif action == 'leave':
                state.update(present=False, reply_mode='paused', link=None,
                             state='leaving' if state['room'] else 'left',
                             leave_confirmed=not bool(state['room']))
            elif action == 'pause':
                state['reply_mode'] = 'paused'
            else:
                state['reply_mode'] = 'chat'
            self.write(db, state)
            db.execute('INSERT INTO commands VALUES(?,?,?)', (rid, digest, state['revision']))
            db.execute('DELETE FROM commands WHERE rowid NOT IN (SELECT rowid FROM commands ORDER BY rowid DESC LIMIT 1024)')
        return dict(self.public(), accepted=True, duplicate=False, command_revision=state['revision'])

    def public(self):
        value = self.read()
        return {'ok': True, 'version': 1, **{k: value[k] for k in (
            'revision', 'present', 'reply_mode', 'state', 'leave_confirmed', 'observed_at', 'error')},
            'chat_available': self.chat_available, 'audio_input': False}


def ack(response):
    """/quit can acknowledge success without returning a data object."""
    if not isinstance(response, dict) or response.get('status') != 1 or response.get('errcode', 0) not in (0, None):
        raise RoomError('酷狗未确认本次退出')


def membership(response):
    if isinstance(response, dict) and response.get('status') == 0 and response.get('errcode') == 20004:
        return False
    ack(response)
    data = response.get('data')
    if not isinstance(data, dict) or data.get('me_online') not in (0, 1):
        raise RoomError('房间成员状态无法核实')
    return data['me_online'] == 1


def leave_known(client, room, *, allow_quit=True, before_quit=lambda: None):
    """No invite lookup/join. Lost receipt is checked, never blindly resent."""
    if not membership(client.status(room)):
        return {'confirmed': True, 'receipt': 'already_left'}
    receipt = 'not_attempted'
    if allow_quit:
        before_quit()
        receipt = 'accepted'
        try:
            ack(client.leave(room, consent=True))
        except RoomError:
            receipt = 'unconfirmed'
    if membership(client.status(room)):
        return {'confirmed': False, 'receipt': receipt}
    return {'confirmed': True, 'receipt': receipt}

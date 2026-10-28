"""Single-attempt room replies, prepared for a verified chat transport.

This module does not install an endpoint or call a model. The caller must
hold the room supervisor's dispatch lock while checking membership/intent and
through sending, so an accepted leave prevents subsequent replies.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
from ordinary_room import RoomError
from native_room import identifier


def message_body(client, room, eid, member, text):
    if not isinstance(member, dict) or str(member.get('userid')) != str(client.userid) or member.get('role') == 1:
        raise RoomError('无法确认发言身份')
    if not isinstance(eid, str) or not eid.isascii() or not eid.isdecimal() or not 1 <= len(eid) <= 32:
        raise RoomError('房间会话编号无效')
    if not isinstance(text, str):
        raise RoomError('回复文字无效')
    text = text.strip()
    if not text or len(text) > 300 or any(ord(c) < 32 and c not in '\n\t' for c in text):
        raise RoomError('回复文字长度或内容无效')
    nick, avatar = member.get('nickname'), member.get('img')
    if not isinstance(nick, str) or not 1 <= len(nick) <= 128 or not isinstance(avatar, str) or len(avatar) > 4096:
        raise RoomError('无法确认发言者资料')
    message = {'msgtype': 801, 'alert': text, 'nickname': nick, 'imgUrl': avatar,
               'gender': member.get('gender', 0), 'sysMsg': 0}
    for key in ('vip_type', 'package_type', 'y_type', 'vip_user_type', 'vip_user_y_type', 's_vip_level'):
        value = member.get(key, 0)
        if type(value) is not int or not 0 <= value <= 100000:
            raise RoomError('发言者展示资料异常')
        message[key] = value
    return dict(client.auth(room), eid=eid, message=message)


class Outbox:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        with self.db() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS sends (key TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL)')
        if os.name != 'nt': self.path.chmod(0o600)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            conn.execute('PRAGMA synchronous=FULL')
            with conn: yield conn
        finally: conn.close()

    def once(self, room, incoming_id, part, text, *, permit, send):
        """Record an attempt before transmission; never replay unknown sends."""
        room = identifier(room, '房间编号')
        incoming_id = identifier(incoming_id, '消息编号')
        if type(part) is not int or not 0 <= part <= 2 or not isinstance(text, str) or not 1 <= len(text.strip()) <= 300:
            raise RoomError('待发送消息无效')
        key = hashlib.sha256(f'{room}:{incoming_id}:{part}'.encode()).hexdigest()
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self.lock:
            with self.db() as conn:
                existing = conn.execute('SELECT digest,state FROM sends WHERE key=?', (key,)).fetchone()
                if existing:
                    if existing[0] != digest: raise RoomError('同一条消息的回复内容发生冲突')
                    return {'state': existing[1], 'duplicate': True}
            # A paused or changed room must not even reserve/send a message.
            permit()
            with self.db() as conn:
                conn.execute('INSERT INTO sends VALUES(?,?,?)', (key,digest,'pending'))
            state = 'uncertain'
            try:
                result = send(text)
                if not isinstance(result, dict): raise RoomError('发送结果无法确认')
                if result.get('status') == 0 and type(result.get('errcode')) is int:
                    state = 'rejected'
                elif result.get('status') == 1 and result.get('errcode', 0) in (0, None):
                    data = result.get('data')
                    if isinstance(data, dict) and data.get('msgid'):
                        state = 'accepted'
            except Exception:
                # Network error could arrive after the service accepted it.
                pass
            with self.db() as conn:
                conn.execute('UPDATE sends SET state=? WHERE key=?', (state,key))
            return {'state': state, 'duplicate': False}

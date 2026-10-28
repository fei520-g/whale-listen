"""Conservative room-text gate, awaiting real room protocol validation.

No network, model invocation, logging of message text, or sending occurs here.
The first observed snapshot establishes a baseline and is never replayed.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from native_room import identifier
from ordinary_room import RoomError


class ChatGate:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as conn:
            conn.executescript('''
              CREATE TABLE IF NOT EXISTS session(id INTEGER PRIMARY KEY CHECK(id=1),
                  room_hash TEXT NOT NULL, start_sec INTEGER NOT NULL, baseline INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS seen(room_hash TEXT NOT NULL, message_hash TEXT NOT NULL,
                  PRIMARY KEY(room_hash, message_hash));
            ''')
            columns={row[1] for row in conn.execute('PRAGMA table_info(session)')}
            if 'cursor' not in columns:conn.execute('ALTER TABLE session ADD COLUMN cursor TEXT')
        if os.name != 'nt': self.path.chmod(0o600)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            conn.execute('PRAGMA synchronous=FULL')
            with conn: yield conn
        finally:
            conn.close()

    def begin(self, room_id):
        """Explicitly start a fresh room session; no historic message replay."""
        room = str(identifier(room_id, '房间编号'))
        hashed = hashlib.sha256(room.encode()).hexdigest()
        with self.lock, self.db() as conn:
            conn.execute('INSERT OR REPLACE INTO session(id,room_hash,start_sec,baseline,cursor) VALUES(1,?,?,0,NULL)', (hashed, int(self.clock())))
        return hashed

    def cursor(self,room_id):
        room=str(identifier(room_id,'房间编号'));hashed=hashlib.sha256(room.encode()).hexdigest()
        with self.lock,self.db() as conn:
            state=conn.execute('SELECT room_hash,baseline,cursor FROM session WHERE id=1').fetchone()
            if state is None or state[0]!=hashed:raise RoomError('房间会话未绑定')
            return state[2] if state[1] else None

    def ingest(self, room_id, owner_id, self_id, members, response, *, newest=False):
        room = str(identifier(room_id, '房间编号'))
        owner = identifier(owner_id, '房主编号')
        me = identifier(self_id, '专用账号编号')
        if owner == me or not isinstance(members, list) or len(members) != 2:
            raise RoomError('成员发生变化，已暂停私人房间回复')
        # Role and identifiers are independently checked; client-provided
        # display-online flags have not been proven reliable.
        if not all(isinstance(m, dict) for m in members):
            raise RoomError('房间成员无法确认')
        owners = [str(m.get('userid')) for m in members if m.get('role') == 1]
        participant_ids = {str(m.get('userid')) for m in members}
        if owners != [str(owner)] or participant_ids != {str(owner), str(me)}:
            raise RoomError('成员发生变化，已暂停私人房间回复')
        if not isinstance(response, dict) or response.get('status') != 1 or response.get('errcode') not in (0, None):
            raise RoomError('房间消息状态不可用')
        rows = response.get('list')
        if not isinstance(rows, list) or len(rows)>49:
            raise RoomError('房间消息过多或格式异常，已暂停回复')
        room_hash = hashlib.sha256(room.encode()).hexdigest()
        tag = 'genting:' + room
        staged = []
        with self.lock, self.db() as conn:
            session = conn.execute('SELECT room_hash,start_sec,baseline,cursor FROM session WHERE id=1').fetchone()
            if session is None or session[0] != room_hash:
                raise RoomError('房间会话未绑定')
            # A full baseline is safe: no old message will be replayed. A full
            # subsequent page may hide a gap, so stop until manually reviewed.
            if session[2] and len(rows)>=49:raise RoomError('新消息过多，已暂停以防遗漏')
            old_cursor=int(session[3]) if session[3] is not None else 0
            largest=old_cursor
            batch_ids=set()
            for item in rows:
                if not isinstance(item, dict) or item.get('tag') != tag:
                    raise RoomError('消息不属于当前房间，已暂停回复')
                try:
                    msg_id = identifier(item.get('msgid'), '消息编号')
                except RoomError:
                    raise RoomError('消息编号无法确认，已暂停回复') from None
                if msg_id in batch_ids or (newest and msg_id<=old_cursor):
                    raise RoomError('新消息游标异常，已暂停回复')
                batch_ids.add(msg_id);largest=max(largest,msg_id)
                digest = hashlib.sha256(str(msg_id).encode()).hexdigest()
                inserted = conn.execute('INSERT OR IGNORE INTO seen VALUES(?,?)', (room_hash, digest)).rowcount
                msg = item.get('message')
                if not inserted or not session[2] or not isinstance(msg, dict): continue
                if str(item.get('uid')) != str(owner) or type(msg.get('msgtype')) is not int or msg['msgtype'] != 801:
                    continue
                stamp, text = item.get('addtime'), msg.get('alert')
                if type(stamp) is not int or stamp < session[1] or stamp > int(self.clock()) + 60:
                    continue
                if msg.get('sysMsg', 0) != 0 or not isinstance(text, str) or not text.strip() or len(text) > 1000:
                    continue
                staged.append({'message_id': str(msg_id), 'at': stamp, 'text': text.strip()})
            conn.execute('UPDATE session SET baseline=1,cursor=? WHERE id=1',(str(largest) if largest else None,))
        # At-most-once processing: the ledger commits before text is returned.
        # Crash between this point and the Agent call may lose a reply; never
        # silently retry an ambiguous model/send operation.
        return sorted(staged, key=lambda row: (row['at'], int(row['message_id'])))

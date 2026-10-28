"""One room chat session coordinator, not started by the live controller.

Calls model only for gate-approved new host messages. Caller must supply a
reviewed model worker and explicitly enabled Store capability before use.
"""
import hashlib
from conversation import answer
from ordinary_room import RoomError, require_success
from chat_sender import send_text


class ChatSession:
    def __init__(self, supervisor, gate, outbox, read_history, complete, read_newest=None):
        self.supervisor,self.gate,self.outbox=supervisor,gate,outbox
        self.history,self.complete=read_history,complete
        self.newest=read_newest
        self.generation=None

    def authorize(self, revision, room):
        state=self.supervisor.store.read()
        if (state['revision']!=revision or not state['present'] or state['room']!=room
                or state['reply_mode']!='chat' or state['state']!='online'):
            return {'reply_mode':'paused','revision':state['revision']}
        return {'reply_mode':'chat','revision':revision}

    def members(self, link, room):
        data=self.supervisor.reader(link)
        members=data.get('member_data',[])
        owners=[m for m in members if isinstance(m,dict) and m.get('role')==1]
        if str(data.get('roomid'))!=str(room) or len(members)!=2 or len(owners)!=1:
            raise RoomError('房间成员变化，已暂停回复')
        owner=owners[0].get('userid')
        owner_hash=hashlib.sha256(str(owner).encode()).hexdigest()
        matches=[m for m in members if isinstance(m,dict) and str(m.get('userid'))==str(self.supervisor.client.userid)]
        if owner_hash!=self.supervisor.owner or len(matches)!=1 or str(owner)==str(self.supervisor.client.userid):
            raise RoomError('无法确认房主和专用账号')
        return members,owner,matches[0]

    def tick(self):
        state=self.supervisor.store.read()
        if not state['present'] or state['reply_mode']!='chat' or state['state']!='online':
            self.generation=None
            return {'state':'paused','received':0,'attempted':0}
        revision,room,link=state['revision'],state['room'],state['link']
        if not room or not link:raise RoomError('房间会话不完整')
        members,owner,_=self.members(link,room)
        if self.generation!=revision:
            self.gate.begin(room);self.generation=revision
        cursor=self.gate.cursor(room)
        incremental=cursor is not None and self.newest is not None
        history=(self.newest(self.supervisor.client,room,cursor) if incremental
                 else self.history(self.supervisor.client,room))
        events=self.gate.ingest(room,owner,self.supervisor.client.userid,members,history,newest=incremental)
        attempted=0
        for event in events:
            def authorize():return self.authorize(revision,room)
            def send(message_id,part,text,expected_revision):
                # Serialize final membership/intent checks and actual request
                # with leave/pause, so none dispatch after acceptance.
                with self.supervisor.dispatch:
                    if authorize().get('reply_mode')!='chat' or expected_revision!=revision:
                        raise RoomError('已暂停，不发送回复')
                    _,_,member=self.members(link,room)
                    status=require_success(self.supervisor.client.status(room))
                    if status.get('status')!=1 or status.get('me_online')!=1:
                        raise RoomError('账号不在房间内，不发送回复')
                    eid=str(status.get('eid',''))
                    return self.outbox.once(room,message_id,part,text,
                        permit=lambda: self._require_current(revision,room),
                        send=lambda content:send_text(self.supervisor.client,room,eid,member,content))
            outcome=answer(event,authorize=authorize,complete=self.complete,send=send)
            attempted+=outcome.get('attempted',0)
            if any(x!='accepted' for x in outcome.get('results',[])):
                raise RoomError('房间回复结果未确认，已暂停')
            if outcome.get('state')!='finished':
                break
        return {'state':'online','received':len(events),'attempted':attempted}

    def _require_current(self,revision,room):
        if self.authorize(revision,room).get('reply_mode')!='chat':raise RoomError('房间回复已暂停')

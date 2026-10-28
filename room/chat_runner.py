"""Opt-in chat polling loop. Not enabled in the deployed controller yet."""
import threading
import uuid
from chat_session import ChatSession
from ordinary_room import RoomError


class ChatRunner:
    def __init__(self,supervisor,gate,outbox,read_history,worker_factory,interval=5,read_newest=None):
        self.supervisor,self.gate,self.outbox=supervisor,gate,outbox
        self.read_history,self.worker_factory=read_history,worker_factory
        self.read_newest=read_newest
        self.interval=max(3,min(30,interval));self.stop_event=threading.Event()
        self.worker=None;self.session=None;self.generation=None

    def _close_worker(self):
        worker,self.worker=self.worker,None
        self.session,self.generation=None,None
        if worker:
            try:worker.close()
            except Exception:pass

    def _pause_current(self,revision):
        current=self.supervisor.store.read()
        if current['revision']!=revision or current['reply_mode']!='chat':return
        try:
            result=self.supervisor.control({'version':1,'action':'pause','request_id':str(uuid.uuid4()),'expected_revision':revision})
            self.supervisor.store.update(result['revision'],error='房间闲聊暂时不可用，已暂停回复')
        except RoomError:pass

    def step(self):
        state=self.supervisor.store.read()
        if not state['present'] or state['state']!='online' or state['reply_mode']!='chat':
            self._close_worker()
            return {'state':'paused'}
        revision=state['revision']
        try:
            if self.generation!=revision:
                self._close_worker()
                self.worker=self.worker_factory()
                # If the user stopped while session startup was in progress,
                # no model request or room send may follow.
                if self.supervisor.store.read()['revision']!=revision:
                    self._close_worker();return {'state':'paused'}
                self.session=ChatSession(self.supervisor,self.gate,self.outbox,self.read_history,self.worker.complete,read_newest=self.read_newest)
                self.generation=revision
            return self.session.tick()
        except Exception:
            self._pause_current(revision)
            self._close_worker()
            return {'state':'paused_after_error'}

    def run(self):
        try:
            while not self.stop_event.is_set():
                self.step()
                self.stop_event.wait(self.interval)
        finally:self._close_worker()

    def stop(self):self.stop_event.set()

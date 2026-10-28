"""Bounded stdio link to the dedicated DSH room worker; no shell invocation."""
import json
import queue
import subprocess
import threading
from ordinary_room import RoomError


class WorkerClient:
    def __init__(self, argv, *, env, timeout=130):
        if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv):
            raise RoomError('独立会话启动参数错误')
        self.proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,bufsize=0)
        self.lines=queue.Queue(maxsize=2)
        self.lock=threading.Lock();self.timeout=timeout;self.closed=False
        threading.Thread(target=self._reader,daemon=True).start()
        self.call({'version':1,'action':'start'})

    def _reader(self):
        try:
            while True:
                raw=self.proc.stdout.readline(16385)
                if not raw or len(raw)>16384 or not raw.endswith(b'\n'):
                    self.lines.put(None);return
                self.lines.put(raw)
        except OSError:
            self.lines.put(None)

    def call(self, request, *, timeout=None):
        data=json.dumps(request,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
        if len(data)>16384:raise RoomError('独立会话请求过大')
        with self.lock:
            if self.closed or self.proc.poll() is not None:raise RoomError('独立会话不可用')
            try:
                self.proc.stdin.write(data);self.proc.stdin.flush()
                line=self.lines.get(timeout=self.timeout if timeout is None else timeout)
                if line is None:raise ValueError('worker disconnected')
                response=json.loads(line)
                if not isinstance(response,dict) or response.get('ok') is not True:raise ValueError('worker rejected')
                return response
            except (OSError,ValueError,queue.Empty):
                # Unknown model results are not retried. Stop this worker and
                # let the owner explicitly resume after reviewing its state.
                self.closed=True
                self._finish()
                raise RoomError('独立会话结果未确认，已暂停回复') from None

    def complete(self, text):
        response=self.call({'version':1,'action':'reply','text':text})
        messages=response.get('messages')
        if not isinstance(messages,list) or not 1<=len(messages)<=3 or any(not isinstance(x,str) or not x.strip() or len(x)>300 for x in messages):
            self.close();raise RoomError('独立会话回复格式异常')
        return messages

    def close(self):
        if self.closed:return
        try:self.call({'version':1,'action':'stop'},timeout=5)
        except RoomError:pass
        self.closed=True
        self._finish()

    def _finish(self):
        if self.proc.poll() is None:
            try:self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=2)
        for stream in (self.proc.stdin,self.proc.stdout):
            try:stream.close()
            except OSError:pass

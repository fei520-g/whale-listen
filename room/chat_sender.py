"""Fixed ordinary-room text sender. Caller must verify room/member/intent.

No retries. The surrounding outbox persists attempts before this is called.
"""
from chat_outbox import message_body

def send_text(client, room, eid, self_member, text):
    body=message_body(client,room,eid,self_member,text)
    return client.transport('chat',client.params(),body)

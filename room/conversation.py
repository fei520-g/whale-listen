"""Staged room conversation coordinator; dependencies must be wired explicitly.

The room-message source and DSH preset are not yet verified in production.
No background loop, credentials, concrete transport or model is started here.
"""
from ordinary_room import RoomError
from native_room import identifier


def validated_parts(output):
    if isinstance(output, str): output = [output]
    if not isinstance(output, list) or not 1 <= len(output) <= 3:
        raise RoomError('回复必须为一至三条文字')
    parts = []
    for text in output:
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 300:
            raise RoomError('回复长度或格式无效')
        if any(ord(c) < 32 and c not in '\n\t' for c in text):
            raise RoomError('回复包含无效字符')
        parts.append(text.strip())
    return parts


def answer(event, *, authorize, complete, send):
    """Reply to one already-gated new owner message.

    authorize() verifies the current room, participant set, explicit chat mode
    and intent revision. send() must check again while holding the supervisor's
    dispatch lock, and use Outbox.once. No ambiguous send is retried.
    """
    if not isinstance(event, dict) or set(event) != {'message_id','at','text'}:
        raise RoomError('需要经过房间消息过滤的新文字')
    message_id = identifier(event['message_id'], '消息编号')
    if type(event['at']) is not int or not isinstance(event['text'], str) or not event['text'].strip() or len(event['text'])>1000:
        raise RoomError('消息格式无效')
    authorization = authorize()
    if not isinstance(authorization, dict) or authorization.get('reply_mode') != 'chat' or type(authorization.get('revision')) is not int:
        return {'state':'paused','sent':0}
    # Model access occurs exactly once for this gated new message; the caller
    # is responsible for untrusted-data boundaries and a dedicated DSH session.
    parts = validated_parts(complete(event['text']))
    results=[]
    for part,text in enumerate(parts):
        fresh=authorize()
        if not isinstance(fresh,dict) or fresh.get('reply_mode')!='chat' or fresh.get('revision')!=authorization['revision']:
            return {'state':'paused','sent':results.count('accepted'),'attempted':len(results),'results':results}
        result=send(message_id,part,text,authorization['revision'])
        if not isinstance(result,dict) or result.get('state') not in ('accepted','rejected','uncertain','pending'):
            raise RoomError('发送结果异常')
        results.append(result['state'])
        if result['state'] != 'accepted':break
    return {'state':'finished','sent':results.count('accepted'),'attempted':len(results),'results':results}

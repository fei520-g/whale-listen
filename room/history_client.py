"""Bounded read-only query for one known ordinary Kugou room tag.

The gateway route is present in the official client's Fanxing history module.
It is the same msgtag service path as the follow-listen history module's old
default, and a successful empty read was observed. Live message schema remains
unverified. Never log the URL: the official protocol puts the token in query.
"""
import json
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from native_room import identifier, sign_android
from ordinary_room import NoRedirect, RoomError

URL = 'https://gateway.kugou.com/msg.mobile/v3/msgtag/history'
NEWEST_URL = 'https://gateway.kugou.com/msg.mobile/v3/msgtag/newest'
MAX_BYTES = 128 * 1024


def _read(client, room_id, *, limit, opener, since=None):
    room = identifier(room_id, '房间编号')
    if type(limit) is not int or not 1 <= limit <= 49:
        raise RoomError('房间历史查询条数无效')
    params = client.params()
    params.update(userid=client.userid, token=client.token, tag='genting:' + str(room), filter=1, pagesize=limit)
    if since is not None:
        params['minid'] = identifier(since, '消息编号')
    params['signature'] = sign_android(params, '')
    request = Request((NEWEST_URL if since is not None else URL) + '?' + urlencode(params), headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    try:
        with (opener or build_opener(NoRedirect())).open(request, timeout=15) as response:
            if response.headers.get('ssa-code'):
                raise RoomError('酷狗要求额外安全验证，已停止')
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise RoomError('房间消息响应过大')
            result = json.loads(raw)
    except HTTPError as exc:
        raise RoomError('房间消息接口请求被拒绝', retryable=exc.code in (429,500,502,503,504)) from None
    except (URLError, OSError):
        raise RoomError('房间消息接口网络或证书验证失败', retryable=True) from None
    except (UnicodeError, ValueError):
        raise RoomError('房间消息响应格式错误') from None
    if not isinstance(result, dict) or result.get('status') != 1 or result.get('errcode') not in (0,None):
        raise RoomError('酷狗未确认房间消息查询')
    if not isinstance(result.get('list'), list) or len(result['list']) > limit:
        raise RoomError('房间消息列表异常')
    return result


def read_room_history(client, room_id, *, limit=49, opener=None):
    return _read(client,room_id,limit=limit,opener=opener)


def read_room_newest(client, room_id, since_id, *, limit=49, opener=None):
    return _read(client,room_id,limit=limit,opener=opener,since=identifier(since_id,'消息编号'))

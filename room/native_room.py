"""Isolated ordinary-Kugou follow-listen account/room compatibility test.

No audio/control/chat APIs, background tasks, server deployment or MCP changes.
Only the user's privately supplied invite can be used by the CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from ordinary_room import (NoRedirect, OrdinaryRoomProbe, PRIVATE, RoomError,
                           invite_code, private_write, require_success,
                           unprotect_credentials)

ANDROID_SALT = "OIlwieks28dk2k092lksi2UIkp"
ENDPOINTS = {op: "https://gateway.kugou.com/yiqiting/genting/v4/musicroom/" + path
             for op, path in {"status": "get_status", "join": "enter", "leave": "quit"}.items()}
ENDPOINTS["heartbeat"] = "https://gateway.kugou.com/yiqiting/genting/v4/member/rpt"
ENDPOINTS["chat"] = "https://gateway.kugou.com/yiqiting/genting/v4/musicroom/message"


def sign_android(params: dict, body: str) -> str:
    if "signature" in params:
        raise RoomError("参数已含签名")
    text = "".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.md5((ANDROID_SALT + text + body + ANDROID_SALT).encode()).hexdigest()


def request_native_json(operation: str, params: dict, body: dict) -> dict:
    if operation not in ENDPOINTS:
        raise RoomError("不允许的原生房间操作")
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    query = dict(params, signature=sign_android(params, text))
    req = Request(ENDPOINTS[operation] + "?" + urlencode(query), data=text.encode(),
                  method="POST", headers={"Content-Type": "application/json;charset=utf-8",
                  "Accept": "application/json", "User-Agent": "Mozilla/5.0",
                  "mid": params["mid"], "dfid": params["dfid"],
                  "clienttime": str(params["clienttime"])})
    try:
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            if response.headers.get("ssa-code"):
                raise RoomError("酷狗要求额外安全验证；已停止")
            raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise RoomError("酷狗房间响应过大")
            result = json.loads(raw)
    except HTTPError as exc:
        raise RoomError(f"房间接口返回 HTTP {exc.code}；未自动重试",
                        retryable=exc.code in (429, 500, 502, 503, 504)) from None
    except (URLError, OSError):
        raise RoomError("房间接口网络连接失败；未自动重试入房", retryable=True) from None
    except (ValueError, UnicodeError):
        raise RoomError("房间接口响应格式异常") from None
    if not isinstance(result, dict):
        raise RoomError("房间接口响应不是对象")
    return result


def identifier(value, label):
    text = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", text):
        raise RoomError(f"{label}格式错误")
    return int(text)


class NativeRoomClient:
    def __init__(self, credentials: dict, *, transport=request_native_json, clock=time.time):
        if credentials.get("platform") != "ordinary":
            raise RoomError("需要普通版账号授权，不能混用概念版")
        self.userid = identifier(credentials.get("userid"), "账号编号")
        self.token = credentials.get("token")
        self.mid = credentials.get("mid")
        if not isinstance(self.token, str) or not 8 <= len(self.token) <= 4096:
            raise RoomError("登录令牌格式错误")
        if not isinstance(self.mid, str) or not re.fullmatch(r"[0-9a-f]{32}", self.mid):
            raise RoomError("登录设备标识格式错误")
        self.transport, self.clock = transport, clock

    def params(self):
        # ParamGenerator.n0().p(json).z0(): auth belongs in JSON, not query.
        return dict(dfid="-", appid=1005, mid=self.mid, uuid="-",
                    clientver=20489, clienttime=int(self.clock()))

    def auth(self, room):
        return {"userid": self.userid, "token": self.token,
                "roomid": identifier(room, "房间编号")}

    def status(self, room) -> dict:
        return self.transport("status", self.params(), dict(self.auth(room), req=1))

    def join(self, room, code: str, *, consent: bool, creator=None) -> dict:
        if not consent:
            raise RoomError("需要用户允许加入指定房间")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", code):
            raise RoomError("邀请代码格式错误")
        body = dict(self.auth(room), enter_frm=11, code=code, supports=2,
                    creator=identifier(creator, "邀请者编号"))
        if body["creator"] == self.userid:
            raise RoomError("扫码账号与房主相同；需要小鲸鱼的独立账号")
        return self.transport("join", self.params(), body)

    def leave(self, room, *, consent: bool):
        if not consent:
            raise RoomError("需要授权退出测试房间")
        return self.transport("leave", self.params(), self.auth(room))

    def heartbeat(self, room, eid: str) -> dict:
        # Official foreground-presence heartbeat; never submit song progress,
        # playback actions or caller-supplied listening-duration counters.
        if not isinstance(eid, str) or not re.fullmatch(r"[0-9]{1,32}", eid):
            raise RoomError("需要当前房间返回的有效会话编号")
        return self.transport("heartbeat", self.params(),
                              dict(self.auth(room), eid=eid, event=1))


def summary(response: dict) -> dict:
    """Do not print arbitrary API responses, tokens, members or identifiers."""
    data = response.get("data")
    data = data if isinstance(data, dict) else {}
    result = {"status": response.get("status"), "errcode": response.get("errcode"),
              "data_fields": sorted(data)}
    for key in ["status", "me_online", "hbt_intval", "followed", "room_type", "live_mode"]:
        value = data.get(key)
        if isinstance(value, (int, bool)):
            result[key if key != "status" else "room_status"] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "join", "leave", "heartbeat"])
    parser.add_argument("--authorized-room-test", action="store_true")
    args = parser.parse_args()
    if not args.authorized_room_test:
        raise RoomError("需要用户授权本次房间兼容性测试")
    account_file = PRIVATE / "ordinary-account.dpapi"
    if not account_file.is_file():
        raise RoomError("请先完成小鲸鱼专用号的扫码授权")
    credentials = unprotect_credentials(account_file.read_bytes())
    client = NativeRoomClient(credentials)
    link = (PRIVATE / "invite-url.txt").read_text().strip()
    # Get fresh official invite details; never fall back to stale eids/room ids.
    captured = {}
    from ordinary_room import request_json
    def capture(op, params):
        response = request_json(op, params)
        captured.update(require_success(response))
        return response
    probe = OrdinaryRoomProbe(client.mid, transport=capture)
    room = probe.inspect(link)
    if args.action == "status":
        response = client.status(room["roomid"])
    elif args.action == "join":
        owners = [m for m in captured.get("members", [])
                  if isinstance(m, dict) and m.get("role") == 1]
        if len(owners) != 1:
            raise RoomError("无法唯一确认邀请者；未入房")
        response = client.join(room["roomid"], invite_code(link), consent=True,
                               creator=owners[0].get("userid"))
    elif args.action == "leave":
        response = client.leave(room["roomid"], consent=True)
    else:
        data = require_success(client.status(room["roomid"]))
        if data.get("me_online") != 1:
            raise RoomError("当前账号不在房间内；未发送心跳")
        response = client.heartbeat(room["roomid"], str(data.get("eid", "")))
    safe = summary(response)
    safe.update({"operation": args.action, "observed_at": time.time()})
    private_write(PRIVATE / f"native-{args.action}-result.json", json.dumps(safe).encode())
    print(json.dumps(safe))
    # HTTP 200 is not success. A server rejection remains a nonzero CLI result.
    require_success(response)


if __name__ == "__main__":
    try:
        main()
    except RoomError as exc:
        print(str(exc))
        raise SystemExit(1) from None

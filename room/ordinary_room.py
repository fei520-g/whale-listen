"""Private, bounded ordinary-Kugou room investigation and QR authorization.

This module does not join rooms, control playback, post messages or run a web
server. Account authorization is a separate, explicit CLI operation. See
SOURCES.md for interoperability evidence and third-party notices.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
H5_SALT = "NVPh5oo715z5DIWAeQlhMDsWXXQV4hwt"
ENDPOINTS = {
    "invite": "https://gateway.kugou.com/yiqiting/genting/v4/musicroom/invite_info_for_h5",
    "qr_create": "https://login-user.kugou.com/v2/qrcode",
    "qr_check": "https://login-user.kugou.com/v2/get_userinfo_qrcode",
}


class RoomError(Exception):
    """A public-safe error: never include URLs, account identifiers or tokens."""
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def sign_web(params: dict, body: str = "") -> str:
    if "signature" in params:
        raise RoomError("参数已含签名，拒绝重复签名")
    text = "".join(sorted(f"{key}={value}" for key, value in params.items()))
    return hashlib.md5((H5_SALT + text + body + H5_SALT).encode()).hexdigest()


def invite_code(link: str) -> str:
    try:
        url = urlsplit(link.strip())
        if (url.scheme != "https" or url.netloc != "h5.kugou.com"
                or url.path != "/sharepage/v-96be9ea4/index.html" or url.fragment):
            raise ValueError()
        values = parse_qs(url.query, keep_blank_values=True).get("code", [])
        if len(values) != 1 or not re.fullmatch(r"[0-9a-fA-F]{32}", values[0]):
            raise ValueError()
        return values[0]
    except (ValueError, TypeError):
        raise RoomError("需要酷狗普通版的原始跟听邀请链接") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RoomError("接口发生重定向，已停止；不会转发登录信息")


def request_json(operation: str, params: dict) -> dict:
    if operation not in ENDPOINTS:
        raise RoomError("不允许的操作")
    signed = dict(params, signature=sign_web(params))
    req = Request(ENDPOINTS[operation] + "?" + urlencode(signed), headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://h5.kugou.com/",
        "Accept": "application/json",
    })
    try:
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            if response.headers.get("ssa-code"):
                raise RoomError("酷狗要求额外安全验证，请使用官方客户端处理")
            raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise RoomError("接口响应过大，已停止")
            data = json.loads(raw)
    except HTTPError as exc:
        raise RoomError(f"酷狗接口返回 HTTP {exc.code}；已停止",
                        retryable=exc.code in (429, 500, 502, 503, 504)) from None
    except (URLError, OSError):
        raise RoomError("酷狗接口网络连接失败；未重试账号操作", retryable=True) from None
    except (ValueError, UnicodeError):
        raise RoomError("酷狗接口响应格式异常") from None
    if not isinstance(data, dict):
        raise RoomError("酷狗接口响应不是对象")
    return data


def require_success(response: dict) -> dict:
    # The invite protocol uses errcode, login protocols use error_code. Do not
    # infer success from HTTP 200 or expose server text (which may contain keys).
    code = response.get("errcode", response.get("error_code", 0))
    if response.get("status") != 1 or code not in (0, None):
        safe_code = str(code) if isinstance(code, int) else "unknown"
        raise RoomError(f"酷狗拒绝请求（错误码 {safe_code}）；未绕过验证")
    data = response.get("data")
    if not isinstance(data, dict):
        raise RoomError("酷狗返回的数据格式异常")
    return data


def private_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(0o600)
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def device_id() -> str:
    path = PRIVATE / "room-client-device-id.txt"
    if not path.exists():
        private_write(path, secrets.token_hex(16).encode())
    value = path.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise RoomError("本地设备标识损坏")
    return value


class OrdinaryRoomProbe:
    def __init__(self, mid: str, transport=request_json, clock=time.time):
        if not re.fullmatch(r"[0-9a-f]{32}", mid):
            raise RoomError("设备标识格式不正确")
        self.mid, self.transport, self.clock = mid, transport, clock

    def base(self) -> dict:
        return dict(dfid="-", mid=self.mid, uuid="-", appid=1005,
                    clientver=20489, clienttime=int(self.clock()))

    def inspect(self, link: str) -> dict:
        params = dict(srcappid=2919, clientver=1000,
                      clienttime=int(self.clock() * 1000), appid=1058,
                      dfid="-", mid=self.mid, uuid="", code=invite_code(link))
        data = require_success(self.transport("invite", params))
        room = str(data.get("roomid", ""))
        if not re.fullmatch(r"[1-9][0-9]{0,19}", room):
            raise RoomError("邀请没有有效房间编号；不会使用 eid 代替")
        members = data.get("members", [])
        if not isinstance(members, list):
            raise RoomError("房间成员数据格式异常")
        # This is private state. The CLI only prints the count.
        return {"roomid": room, "members": len(members), "checked_at": self.clock()}

    def create_challenge(self) -> dict:
        params = dict(self.base(), appid=1001, type=1, plat=4, srcappid=2919,
                      qrcode_txt="https://h5.kugou.com/apps/loginQRCode/html/index.html?appid=1005&")
        data = require_success(self.transport("qr_create", params))
        key, image = data.get("qrcode"), data.get("qrcode_img")
        if not isinstance(key, str) or not re.fullmatch(r"[\w-]{16,128}", key):
            raise RoomError("登录二维码标识格式异常")
        if not isinstance(image, str) or not image.startswith("data:image/png;base64,"):
            raise RoomError("登录二维码不是 PNG 图像")
        try:
            png = base64.b64decode(image.split(",", 1)[1], validate=True)
        except ValueError:
            raise RoomError("登录二维码编码异常") from None
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > 128 * 1024:
            raise RoomError("登录二维码图像异常")
        return {"key": key, "created_at": self.clock(), "png": png}

    def check_authorization(self, challenge: dict, *, consent: bool) -> dict:
        if not consent:
            raise RoomError("需要用户明确授权登录小鲸鱼的酷狗账号")
        age = self.clock() - float(challenge.get("created_at", 0))
        key = challenge.get("key")
        if age < 0 or age > 180 or not isinstance(key, str) or not re.fullmatch(r"[\w-]{16,128}", key):
            raise RoomError("二维码已过期，请生成新的二维码")
        params = dict(self.base(), plat=4, srcappid=2919, qrcode=key)
        data = require_success(self.transport("qr_check", params))
        state = data.get("status")
        if state in (0, 1, 2):
            return {"state": {0: "expired", 1: "waiting_scan", 2: "waiting_confirm"}[state]}
        if state != 4:
            raise RoomError("未知登录状态；已停止")
        userid, token = str(data.get("userid", "")), data.get("token")
        if (not re.fullmatch(r"[1-9][0-9]{0,19}", userid)
                or not isinstance(token, str) or not 8 <= len(token) <= 4096):
            raise RoomError("登录凭证格式异常")
        excluded = challenge.get("excluded_userid_hash")
        if excluded is not None:
            if not isinstance(excluded, str) or not re.fullmatch(r"[0-9a-f]{64}", excluded):
                raise RoomError("账号隔离约束损坏，请重新生成二维码")
            if hashlib.sha256(userid.encode()).hexdigest() == excluded:
                raise RoomError("本次授权仍是你的房主号；未保存凭证，请改用小鲸鱼专用号")
        # No server output, JSON logging or unencrypted credentials on disk.
        return {"state": "authorized", "credentials": {
            "userid": userid, "token": token, "mid": self.mid,
            "platform": "ordinary", "created_at": self.clock(),
        }}


def protect_credentials(credentials: dict) -> bytes:
    """Windows user-bound DPAPI; fail closed on unsupported hosts."""
    if os.name != "nt":
        raise RoomError("本地登录工具仅支持 Windows DPAPI 加密存储")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    raw = json.dumps(credentials, ensure_ascii=False).encode()
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not crypt.CryptProtectData(ctypes.byref(source), "Whale music private login",
                                 None, None, None, 1, ctypes.byref(output)):
        raise RoomError("Windows 凭证加密失败；未保存明文")
    try:
        return b"WMKG1\n" + base64.b64encode(ctypes.string_at(output.data, output.size))
    finally:
        kernel.LocalFree(output.data)


def unprotect_credentials(encrypted: bytes) -> dict:
    """Decrypt only in this Windows user's security context; never log values."""
    if os.name != "nt" or not encrypted.startswith(b"WMKG1\n"):
        raise RoomError("不是本机支持的加密登录文件")
    try:
        raw = base64.b64decode(encrypted.split(b"\n", 1)[1], validate=True)
    except ValueError:
        raise RoomError("加密登录文件损坏") from None
    if not raw or len(raw) > 64 * 1024:
        raise RoomError("加密登录文件大小异常")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None,
                                   None, 1, ctypes.byref(output)):
        raise RoomError("无法解密登录文件；需要原 Windows 用户")
    try:
        data = json.loads(ctypes.string_at(output.data, output.size))
    except (ValueError, UnicodeError):
        raise RoomError("解密后的登录数据格式异常") from None
    finally:
        kernel.LocalFree(output.data)
    if not isinstance(data, dict):
        raise RoomError("解密后的登录数据格式异常")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "qr-create", "qr-check"])
    parser.add_argument("--authorized-login", action="store_true",
                        help="Only after the human has explicitly authorized this account login")
    parser.add_argument("--separate-from-current-account", action="store_true",
                        help="Replace a mistakenly authorized account; reject that account on the new QR")
    args = parser.parse_args()
    client = OrdinaryRoomProbe(device_id())
    if args.action == "inspect":
        result = client.inspect((PRIVATE / "invite-url.txt").read_text().strip())
        private_write(PRIVATE / "ordinary-room.json", json.dumps(result).encode())
        print(json.dumps({"invite_valid": True, "members": result["members"]}))
    elif args.action == "qr-create":
        excluded = None
        account_file = PRIVATE / "ordinary-account.dpapi"
        if args.separate_from_current_account:
            if not account_file.is_file():
                raise RoomError("没有可供核对的旧账号凭证")
            old = unprotect_credentials(account_file.read_bytes())
            excluded = hashlib.sha256(str(old["userid"]).encode()).hexdigest()
            # Keep existing credentials until a new login is authorized.
            private_write(PRIVATE / "excluded-host-account.sha256", excluded.encode())
        elif (PRIVATE / "excluded-host-account.sha256").is_file():
            excluded = (PRIVATE / "excluded-host-account.sha256").read_text().strip()
        challenge = client.create_challenge()
        if excluded:
            challenge["excluded_userid_hash"] = excluded
        image = challenge.pop("png")
        private_write(PRIVATE / "ordinary-login-challenge.json", json.dumps(challenge).encode())
        private_write(PRIVATE / "ordinary-login-qr.png", image)
        print("已生成登录二维码；仅生成二维码，不会自动登录或入房")
    else:
        challenge = json.loads((PRIVATE / "ordinary-login-challenge.json").read_text())
        result = client.check_authorization(challenge, consent=args.authorized_login)
        if result["state"] == "authorized":
            encrypted = protect_credentials(result.pop("credentials"))
            private_write(PRIVATE / "ordinary-account.dpapi", encrypted)
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except RoomError as exc:
        print(str(exc))
        raise SystemExit(1) from None

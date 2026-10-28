"""Forced-SSH stdin JSON -> fixed private Unix socket. Never executes argv.

Install with a separate restricted key/account, never broaden the existing
upload-only music key. This program cannot read Kugou credentials or SQLite.
"""
import argparse
import json
import signal
import socket
import sys


def exchange(path, request):
    if not isinstance(request, dict) or request.get('action') not in ('status', 'join', 'leave', 'pause', 'chat'):
        raise ValueError('unsupported_action')
    raw = json.dumps(request, ensure_ascii=False).encode() + b'\n'
    if len(raw) > 4096:
        raise ValueError('request_too_large')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(20)
        conn.connect(str(path))
        conn.sendall(raw)
        with conn.makefile('rb') as stream:
            reply = stream.readline(4097)
    if len(reply) > 4096 or not reply.endswith(b'\n'):
        raise ValueError('invalid_response')
    return json.loads(reply)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--socket', required=True)
    args = parser.parse_args()
    if hasattr(signal, 'SIGALRM'):
        signal.alarm(25)
    try:
        raw = sys.stdin.buffer.readline(4097)
        if len(raw) > 4096 or not raw.endswith(b'\n'):
            raise ValueError('invalid_request')
        result = exchange(args.socket, json.loads(raw))
    except (ValueError, TypeError, OSError):
        result = {'ok': False, 'error': 'room_control_unavailable'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok') else 2


if __name__ == '__main__': sys.exit(main())

"""向运行中的 YuriArm 指令服务器发送一条指令（JSON 行协议）。

用法:
    python tools/send_command.py --cmd telemetry
    python tools/send_command.py --cmd move_joints --params '{"targets":{"shoulder_lift":30},"duration":2}'
    python tools/send_command.py --raw '{"cmd":"estop"}'
    echo '{"cmd":"ping"}' | python tools/send_command.py --stdin
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> int:
    from yuriarm.config import load_config

    ap = argparse.ArgumentParser(description="向 YuriArm 指令服务器发送 JSON 指令")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--cmd", default=None, help="指令名（如 move_joints / estop / telemetry）")
    ap.add_argument("--params", default=None, help='JSON 参数 dict')
    ap.add_argument("--raw", default=None, help="原始指令 JSON（优先于 --cmd/--params）")
    ap.add_argument("--stdin", action="store_true", help="从标准输入读取指令 JSON")
    args = ap.parse_args(argv)

    cfg = load_config()
    host = args.host or cfg.server["host"]
    port = int(args.port or cfg.server["port"])

    if args.raw:
        raw = args.raw
    elif args.stdin:
        raw = sys.stdin.read().strip()
        if not raw:
            print("stdin 为空", file=sys.stderr)
            return 2
    elif args.cmd:
        params = json.loads(args.params) if args.params else {}
        raw = json.dumps({"cmd": args.cmd, "params": params})
    else:
        print("需要 --raw / --cmd / --stdin 之一", file=sys.stderr)
        return 2

    try:
        with socket.create_connection((host, port), timeout=5.0) as sock:
            sock.sendall((raw + "\n").encode("utf-8"))
            buf = sock.recv(65536).decode("utf-8", errors="replace")
    except OSError as e:
        print(f"连接失败 {host}:{port}: {e}", file=sys.stderr)
        return 1

    try:
        parsed = json.loads(buf)
    except json.JSONDecodeError:
        print(buf)
        return 1
    print(json.dumps(parsed, ensure_ascii=False, indent=2, default=str))
    return 0 if parsed.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

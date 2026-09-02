"""ESP32-S3 无线执行端冒烟测试：TCP 或 USB 串口两种通道（需已烧录固件并启动）。

用法:
    python tools/esp32_smoke.py --host 192.168.4.1            # WiFi TCP
    python tools/esp32_smoke.py --serial COM18                # USB 串口（不占用 WiFi）
    python tools/esp32_smoke.py --serial COM18 --move '{"shoulder_lift":30}' --duration 2
    python tools/esp32_smoke.py --serial COM18 --ping-only
    python tools/esp32_smoke.py --serial COM19 --diag

说明: 固件按协议.md 要求"200ms 无指令/心跳即停"，脚本后台每 100ms 发 ping 喂狗；
测试结束发 estop 关力矩（安全）。
"""
from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TcpTransport:
    def __init__(self, host: str, port: int):
        self.sock = socket.create_connection((host, port), timeout=5.0)

    def send_raw(self, data: bytes) -> None:
        self.sock.sendall(data)

    def recv_line(self, timeout: float = 5.0) -> dict:
        self.sock.settimeout(timeout)
        buf = b""
        while b"\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("连接被关闭")
            buf += chunk
        line, _, rest = buf.partition(b"\n")
        return json.loads(line.decode("utf-8"))

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200):
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.5, write_timeout=3.0)
        self._lock = threading.Lock()

    def send_raw(self, data: bytes) -> None:
        with self._lock:
            self.ser.write(data)
            self.ser.flush()

    def recv_line(self, timeout: float = 5.0) -> dict:
        """读一行；跳过非 JSON 行（启动日志/安全消息）。"""
        self.ser.timeout = 0.1
        buf = b""
        t0 = time.time()
        while time.time() - t0 < timeout:
            chunk = self.ser.read(1024)
            if chunk:
                buf += chunk
                while b"\n" in buf:
                    line, _, buf = buf.partition(b"\n")
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        return json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue  # 日志行，跳过
        raise TimeoutError("串口响应超时")

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass


def send(t: TcpTransport | SerialTransport, cmd: str, params: dict | None = None, cid: int = 1) -> dict:
    msg = {"id": cid, "cmd": cmd, "params": params or {}}
    t.send_raw((json.dumps(msg) + "\n").encode("utf-8"))
    while True:
        r = t.recv_line()
        if r.get("id") == cid or "id" not in r:
            return r  # 忽略心跳 ping 的回复


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.4.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--serial", default=None, help="USB 串口（如 COM18），优先于 TCP")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--move", default=None, help='move_joints targets JSON')
    ap.add_argument("--duration", type=float, default=2.0)
    ap.add_argument("--diag", action="store_true", help="发送 bus_diag 并退出")
    ap.add_argument("--scan", action="store_true", help="发送 bus_scan 全 ID 扫描并退出")
    ap.add_argument("--raw", action="store_true", help="发送 bus_raw 原始字节诊断并退出")
    ap.add_argument("--no-estop", action="store_true")
    ap.add_argument("--ping-only", action="store_true")
    args = ap.parse_args()

    if args.serial:
        print(f"[*] 打开串口 {args.serial} ...")
        t: TcpTransport | SerialTransport = SerialTransport(args.serial, args.baud)
        print("[+] 已打开")
    else:
        print(f"[*] 连接 {args.host}:{args.port} ...")
        t = TcpTransport(args.host, args.port)
        print("[+] 已连接")

    stop = threading.Event()

    def heartbeat():
        cid = 100
        while not stop.is_set():
            try:
                t.send_raw((json.dumps({"id": cid, "cmd": "heartbeat", "params": {}}) + "\n").encode("utf-8"))
            except OSError:
                break
            cid += 1
            stop.wait(0.1)

    hb = None
    if args.move:
        hb = threading.Thread(target=heartbeat, daemon=True)
        hb.start()

    try:
        r = send(t, "ping")
        print("[ping]", json.dumps(r, ensure_ascii=False))
        if args.ping_only:
            return 0 if r.get("ok") else 1

        r = send(t, "status")
        print("[status]", json.dumps(r, ensure_ascii=False))

        if args.diag:
            r = send(t, "bus_diag")
            print("[bus_diag]", json.dumps(r, ensure_ascii=False))
            return 0 if r.get("ok") else 1

        if args.scan:
            r = send(t, "bus_scan")
            print("[bus_scan]", json.dumps(r, ensure_ascii=False))
            return 0 if r.get("ok") else 1

        if args.raw:
            r = send(t, "bus_raw")
            print("[bus_raw]", json.dumps(r, ensure_ascii=False))
            return 0 if r.get("ok") else 1

        if args.move:
            targets = json.loads(args.move)
            r = send(t, "move_joints", {"targets": targets, "duration": args.duration})
            print(f"[move_joints] {json.dumps(r, ensure_ascii=False)}")
            print(f"[*] 等待运动完成 {args.duration}s（心跳喂狗中）...")
            time.sleep(args.duration + 1.0)

        r = send(t, "telemetry")
        print("[telemetry]", json.dumps(r, ensure_ascii=False))
        return 0
    finally:
        if not args.no_estop:
            try:
                r = send(t, "estop")
                print("[estop]", json.dumps(r, ensure_ascii=False))
            except Exception as e:
                print(f"[estop] 失败: {e}")
        stop.set()
        if hb is not None:
            hb.join(timeout=2.0)
        t.close()
        print("[*] 通道关闭")


if __name__ == "__main__":
    raise SystemExit(main())




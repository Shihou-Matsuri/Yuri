"""WiFi 诊断：连 ESP32 AP 发 car_drive + move_joints 并读 ESP32 响应/错误。

用法（连上 YuriArm-AP 后）:
    python wifi_diag.py
输出会打印每条指令的 ESP32 响应，含 error 字段，定位为何不驱动。
"""
import socket
import json
import time

HOST = "192.168.4.1"
PORT = 8765


def send_and_recv(sock, obj, timeout=2.0):
    sock.settimeout(timeout)
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    sock.settimeout(timeout)
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                line, _, rest = buf.partition(b"\n")
                return line.decode("utf-8", errors="ignore").strip()
        except socket.timeout:
            break
    return buf.decode("utf-8", errors="ignore").strip()


def main():
    print(f"[diag] 连接 {HOST}:{PORT} ...")
    sock = socket.create_connection((HOST, PORT), timeout=5)
    print("[diag] 已连接\n")

    steps = [
        ("全局 resume", {"cmd": "resume", "params": {}}),
        ("car_resume", {"cmd": "car_resume", "params": {}}),
        ("car_status(驱动前)", {"cmd": "car_status", "params": {}}),
        ("car_drive ID7=500", {"cmd": "car_drive", "params": {"raw": [500, 0, 0]}}),
        ("car_status(驱动中)", {"cmd": "car_status", "params": {}}),
        ("car_drive 全0", {"cmd": "car_drive", "params": {"raw": [0, 0, 0]}}),
        ("car_stop", {"cmd": "car_stop", "params": {}}),
        ("move_joints gripper=80", {"cmd": "move_joints", "params": {"targets": {"gripper": 80}, "duration": 0.5}}),
        ("telemetry(arm)", {"cmd": "telemetry", "params": {}}),
    ]
    for name, cmd in steps:
        resp = send_and_recv(sock, cmd)
        print(f"--- {name} ---")
        print(f"    响应: {resp[:300]}\n")
        time.sleep(0.5)

    print("[diag] 完成")
    sock.close()


if __name__ == "__main__":
    main()

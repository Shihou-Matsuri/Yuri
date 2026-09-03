"""WiFi 遥操作诊断：主动臂(COM7/USB)读角度 → WiFi 发 move_joints 到 ESP32 → 从动臂跟随?

用法（连上 YuriArm-AP 后，ESP32 可插 USB 也可纯 WiFi）:
    python wifi_teleop_diag.py
转主动臂，看从动臂是否跟随，以及 ESP32 是否回错误。

注意：本脚本主动臂走 USB(COM7)，ESP32 走 WiFi(TCP)。若 ESP32 没插 USB 也 OK（WiFi 独立）。
"""
import json
import socket
import sys
import time

HOST = "192.168.4.1"
PORT = 8765
LEADER_PORT = "COM7"
SEND_HZ = 10


def make_leader(port):
    import sys as _sys
    from pathlib import Path
    _ARM = Path(__file__).resolve().parents[1]  # YuriArm/
    if str(_ARM) not in _sys.path:
        _sys.path.insert(0, str(_ARM))
    from tools.leader_remote import _make_leader
    return _make_leader(port, mock=False)


def main():
    print(f"[diag] 连主动臂 {LEADER_PORT} (USB) ...")
    leader = make_leader(LEADER_PORT)
    leader.connect(calibrate=False)
    a = leader.get_action()
    print("[diag] 主动臂读数:", {k[:-4]: round(v, 1) for k, v in a.items()})

    print(f"[diag] 连 ESP32 WiFi {HOST}:{PORT} ...")
    sock = socket.create_connection((HOST, PORT), timeout=5)
    sock.settimeout(1.0)
    print("[diag] 已连接 WiFi")

    # 清 estop
    for cmd in ({"cmd": "resume"}, {"cmd": "car_resume"}):
        sock.sendall((json.dumps(cmd) + "\n").encode())
        time.sleep(0.3)

    print("[diag] 请转动主动臂, 观察从动臂是否跟随 (10 秒)...\n")
    errors = []
    t0 = time.time()
    last_target = None
    sent = 0
    while time.time() - t0 < 10:
        action = leader.get_action()
        targets = {k[:-4]: round(float(v), 1) for k, v in action.items() if k.endswith(".pos")}
        # 去掉 gripper 外的都在 -100..100, gripper 0..100
        mj = {"cmd": "move_joints", "params": {"targets": targets, "duration": 0.3}}
        sock.sendall((json.dumps(mj) + "\n").encode())
        sent += 1
        # 读响应看是否报错
        try:
            resp = sock.recv(4096)
            if resp:
                for line in resp.decode(errors="ignore").splitlines():
                    if '"error":null' not in line and '"error":' in line:
                        errors.append(line.strip())
        except socket.timeout:
            pass
        # 打印读数变化
        if last_target is None or any(abs(targets.get(j, 0) - last_target.get(j, 0)) > 5 for j in targets):
            print(f"t={time.time()-t0:.1f}s 目标: shoulder_pan={targets['shoulder_pan']} shoulder_lift={targets['shoulder_lift']} elbow={targets['elbow_flex']} gripper={targets['gripper']}", flush=True)
        last_target = targets
        time.sleep(1.0 / SEND_HZ)

    print(f"\n[diag] 共发 {sent} 条 move_joints")
    print(f"[diag] ESP32 错误: {errors if errors else '(无 - 从动臂应已跟随)'}")
    sock.close()
    leader.disconnect()


if __name__ == "__main__":
    main()

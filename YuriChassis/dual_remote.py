"""轮子 + 机械臂同时控制（键盘控车 + 主动臂遥操作从动臂）。

链路: 笔记本 --WiFi TCP(192.168.4.1:8765) / USB串口(115200)--> ESP32-S3
          ├── UART1 → 从动臂 6×STS3215（主动臂 COM7 遥操作，teleop_joints 直写）
          └── UART2 → 小车 3 舵机 ID 7/8/9（键盘，car_drive 电机恒速）

单循环 20Hz 交替处理两路（不线程化，避免共享串口/TCP 并发）：
    1. bridge.step()  读主动臂 → 变化则发 teleop_joints（机械臂跟随）
    2. 键盘           W/S 前后 A/D 横移 Z/X 旋转 空格停 E 急停 Q 退出
    3. heartbeat     每周期发，喂固件看门狗（从动臂 + 小车）
    4. car_drive     轮子目标非零才发（零时 heartbeat 已喂小车看门狗）

按键说明:
    机械臂: 直接手握主动臂操作（不需要键盘）
    轮子:   W/S前后 A/D横移 Z/X旋转 空格停 E急停 Q退出

安全:
    - 机械臂与小车共用 ESP32 但走不同 UART（UART1/UART2 独立），
      协议层不互斥；但舵机电流叠加，供电须足够（首测车体抬空）。
    - 退出/Ctrl+C: 小车清 0 速刹停 + 全局 estop（从动臂扭矩关）。
    - 连接断开自动重连（TCP），重连后 resume + car_resume。

用法:
    python dual_remote.py                        # 默认 WiFi TCP
    python dual_remote.py --serial COM8          # USB 串口连 ESP32
    python dual_remote.py --leader-port COM7     # 主动臂口（默认 COM7）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ---- 复用路径 ----
_HERE = Path(__file__).resolve()
_YURICHASSIS = _HERE.parent  # YuriChassis/
_YURIARM = _HERE.parents[1] / "YuriArm"
for _p in (_YURICHASSIS, _YURIARM):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import kiwi_drive  # noqa: E402  YuriChassis：运动学 + 键位
from car_remote import (  # noqa: E402
    CAR_SERVO_ORDER,
    RemoteStop,
    SerialTransport,
    TcpTransport,
    build_speeds,
    encode_command,
    send_car_stop,
)

from yuriarm.config import DEFAULT_CONFIG_PATH, JOINT_NAMES, load_config  # noqa: E402
from yuriarm.leader_bridge import LeaderBridge  # noqa: E402
from tools.leader_remote import _make_leader  # noqa: E402

TICK_HZ = 20.0
SEND_PERIOD = 1.0 / TICK_HZ


def _load_bridge() -> LeaderBridge:
    """按 leader.json/arm.json 构建直写遥操作桥（teleop_joints）。"""
    conf = json.loads((_YURIARM / "configs" / "leader.json").read_text(encoding="utf-8"))
    leader_cfg = conf["leader"]
    arm_cfg = load_config(DEFAULT_CONFIG_PATH)
    safety = arm_cfg.safety
    limits = {
        m: (float(safety["joint_limits"][m][0]), float(safety["joint_limits"][m][1]))
        for m in JOINT_NAMES
    }
    return LeaderBridge(
        joint_limits=limits,
        max_velocity=float(leader_cfg.get("max_velocity", 60.0)),
        deadband=float(leader_cfg.get("deadband", 0.5)),
        read_hz=float(leader_cfg.get("read_hz", 30.0)),
        send_hz=float(leader_cfg.get("send_hz", 20.0)),
        move_duration_s=float(leader_cfg.get("move_duration_s", 0.15)),
        estop_tolerance_s=float(leader_cfg.get("estop_tolerance_s", 1.0)),
        apply_speed_limit=False,
        cmd_name="teleop_joints",
    )


class _JsonTransport:
    """把 dict/bytes 都转成行分隔 JSON bytes 再交给底层 transport。

    car_remote 的 TcpTransport/SerialTransport.send 只收 bytes（调用方自行编码），
    而 LeaderBridge.step 直接 send dict——dual_remote 两者混用，这里统一适配。
    """

    def __init__(self, raw):
        self._raw = raw

    def send(self, obj) -> None:
        if isinstance(obj, (bytes, bytearray)):
            data = bytes(obj)
        elif isinstance(obj, str):
            data = obj.encode("utf-8")
        else:
            data = (json.dumps(obj) + "\n").encode("utf-8")
        self._raw.send(data)

    def ping_ok(self, *a, **kw):
        return self._raw.ping_ok(*a, **kw)

    def reconnect(self):
        self._raw.reconnect()

    def close(self):
        self._raw.close()


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("键盘输入仅实现 Windows（msvcrt）")
    import msvcrt

    ap = argparse.ArgumentParser(description="轮子(键盘) + 机械臂(主动臂遥操作) 同时控制")
    ap.add_argument("--host", default="192.168.4.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--serial", default=None, help="USB 串口连 ESP32（如 COM8），走串口而非 TCP")
    ap.add_argument("--leader-port", default=None, help="主动臂串口（默认读 leader.json）")
    args = ap.parse_args()

    raw_transport = (
        SerialTransport(args.serial) if args.serial else TcpTransport(args.host, args.port)
    )
    transport = _JsonTransport(raw_transport)
    link_name = f"串口 {args.serial}" if args.serial else f"TCP {args.host}:{args.port}"

    # ---- 主动臂 + 桥 ----
    leader_cfg = json.loads((_YURIARM / "configs" / "leader.json").read_text(encoding="utf-8"))
    leader_port = args.leader_port or leader_cfg["leader"].get("port", "COM7")
    print(f"[dual_remote] 连接主动臂 {leader_port} ...")
    leader = _make_leader(leader_port, mock=False)
    leader.connect(calibrate=False)
    bridge = _load_bridge()

    # 清 estop 残留
    transport.send(b'{"cmd":"resume"}\n')
    transport.send(b'{"cmd":"car_resume"}\n')

    print(f"[dual_remote] 已连接 {link_name}（{TICK_HZ:.0f}Hz）")
    print("机械臂=手握主动臂 | 轮子: W/S前后 A/D横移 Z/X旋转 空格停 E急停 Q退出 —— 车体抬空首测！")

    motion = None           # 当前轮子运动（None=停）
    car_estop_active = False
    stop_reason = RemoteStop.QUIT
    last_tick = 0.0
    last_ping = 0.0

    try:
        while True:
            now = time.monotonic()
            if now - last_tick >= SEND_PERIOD:
                last_tick = now

                # 1. 机械臂：读主动臂 → 变化则 teleop_joints
                bridge.step(leader, transport)

                # 2. 轮子：目标非零才发 car_drive（零速由 heartbeat 喂狗保持刹停）
                if motion is not None:
                    vx, vy, omega = kiwi_drive.MOTION_VECTORS[motion]
                    speeds = build_speeds(vx, vy, omega)
                    transport.send(encode_command(speeds))

                # 3. heartbeat 喂固件看门狗（从动臂 + 小车）
                transport.send(b'{"cmd":"heartbeat"}\n')

            # 键盘（每 tick 轮询，非阻塞）
            while msvcrt.kbhit():
                key = msvcrt.getch().decode("ascii", errors="ignore").lower()
                if key == "q":
                    motion = None
                    stop_reason = RemoteStop.QUIT
                    print("\n[dual_remote] Q -> 退出")
                    transport.send(b'{"cmd":"car_drive","params":{"raw":[0,0,0]}}\n')
                    transport.send(b'{"cmd":"estop"}\n')
                    return 0
                if key == "e":
                    motion = None
                    car_estop_active = True
                    print("[dual_remote] E -> 急停")
                    transport.send(b'{"cmd":"estop"}\n')   # 全局急停（臂+车）
                    transport.send(b'{"cmd":"car_stop"}\n')
                    continue
                if key == " ":
                    motion = None
                    print("[dual_remote] 停")
                    continue
                new_motion = kiwi_drive.KEY_MOTIONS.get(key)
                if new_motion is not None:
                    if car_estop_active:
                        transport.send(b'{"cmd":"resume"}\n')
                        transport.send(b'{"cmd":"car_resume"}\n')
                        car_estop_active = False
                        print("[dual_remote] 已恢复(resume)")
                    motion = new_motion
                    print(f"[dual_remote] 轮子: {motion.value}")

            # 连接健康检测（TCP 静默断开自动重连）
            if now - last_ping >= 1.0 and not args.serial:
                last_ping = now
                if not transport.ping_ok():
                    print("[dual_remote] 连接断开 -> 自动重连 ...")
                    transport.reconnect()
                    transport.send(b'{"cmd":"resume"}\n')
                    transport.send(b'{"cmd":"car_resume"}\n')
                    print("[dual_remote] 已重连")

            time.sleep(0.004)
    except KeyboardInterrupt:
        stop_reason = RemoteStop.QUIT
        print("\n[dual_remote] Ctrl+C")
    except (ConnectionError, OSError) as exc:
        stop_reason = RemoteStop.ERROR
        print(f"\n[dual_remote] 连接中断: {exc}")
    finally:
        # 收尾：小车刹停（保扭矩防溜坡）+ 机械臂 estop（关扭矩）
        try:
            transport.send(b'{"cmd":"car_drive","params":{"raw":[0,0,0]}}\n')
            transport.send(b'{"cmd":"estop"}\n')
            print(f"[dual_remote] 已刹停 + 机械臂 estop（{stop_reason.value}）")
        except (ConnectionError, OSError):
            pass
        try:
            leader.disconnect()
        except Exception:  # noqa: BLE001
            pass
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

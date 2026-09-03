"""三轮 kiwi 底盘 WiFi 无线键盘遥控（经 Yuri ESP32-S3 执行端）。

链路: 笔记本 --WiFi TCP--> ESP32-S3 --UART2--> 3×STS3215（电机恒速模式）

复用同目录 kiwi_drive.py 的运动学（wheel_rpm / rpm_to_raw）与键位定义。
无线协议走固件 car_drive 指令（持续速度语义），需要固件 ≥ commit 7eb622f。

用法:
    python car_remote.py                 # 默认 WiFi TCP 192.168.4.1:8765
    python car_remote.py --host 192.168.4.1 --port 8765
    python car_remote.py --serial COM5   # 改走 USB 串口（烧录/调试用，非无线）

按键（按住触发一次，保持该运动直到换键/停止）:
    W/S 前后   A/D 横移   Z/X 旋转   空格 停   E 急停(car_stop)   Q 退出

安全:
    - 首测务必车体抬空，确认三轮方向后再落地（见 kiwi_drive.py 标定说明）。
    - car_drive 是持续速度：脚本以 20Hz 持续下发，断连或退出时固件
      500ms 无指令会自动清 0 速刹停（保持扭矩防溜坡），脚本退出也会先 car_stop。
    - 与机械臂互斥：行驶期间从动臂不得动作（半双工总线同一时刻只能一条总线工作）。
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from enum import Enum

import kiwi_drive  # 同目录：运动学 + 键位（wheel_rpm / rpm_to_raw / KEY_MOTIONS）

# ---------- 链路参数 ----------
DEFAULT_HOST = "192.168.4.1"   # ESP32-S3 WiFi AP 地址
DEFAULT_PORT = 8765            # YuriArm TCP 端口（见 firmware/config.h）
TICK_HZ = 20                   # 持续下发频率（≥2Hz 喂看门狗，20Hz 手感平滑）
SEND_TIMEOUT_S = 3.0

# 与固件 CAR_SERVO_IDS = {7,8,9} 顺序一致（car_drive 的 raw 数组按此顺序）
CAR_SERVO_ORDER = (7, 8, 9)


class RemoteStop(Enum):
    """退出原因，决定收尾动作。"""
    QUIT = "quit"        # 正常退出：car_stop + 扭矩关
    ERROR = "error"      # 异常退出：同上


def build_speeds(vx: float, vy: float, omega: float) -> list[int]:
    """车体速度 (vx, vy, omega) -> 每轮 raw speed 数组（按 CAR_SERVO_ORDER）。

    复用 kiwi_drive 的逆运动学：wheel_rpm 返回 {servo_id: rpm}，
    rpm_to_raw 做 ±1800 限幅，DIRECTION 修正物理装反的轮。
    """
    rpms = kiwi_drive.wheel_rpm(vx, vy, omega)
    return [kiwi_drive.rpm_to_raw(rpms[sid]) * kiwi_drive.DIRECTION[sid]
            for sid in CAR_SERVO_ORDER]


def encode_command(speeds: list[int]) -> bytes:
    """组 car_drive 指令行（raw 数组顺序 = CAR_SERVO_IDS 7/8/9）。"""
    cmd = {"cmd": "car_drive", "params": {"raw": speeds}}
    return (json.dumps(cmd) + "\n").encode("utf-8")


class Transport:
    """指令通道：TCP（默认）或 USB 串口（--serial）。send 失败抛 ConnectionError。"""

    def send(self, data: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class TcpTransport(Transport):
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port), timeout=SEND_TIMEOUT_S)

    def send(self, data: bytes) -> None:
        self.sock.sendall(data)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class SerialTransport(Transport):
    def __init__(self, port: str, baud: int = 1000000) -> None:
        import serial

        self.ser = serial.Serial(port, baud, timeout=0.2)

    def send(self, data: bytes) -> None:
        self.ser.write(data)

    def close(self) -> None:
        try:
            self.ser.close()
        except OSError:
            pass


def send_car_stop(transport: Transport) -> None:
    """急停：car_stop（刹停 + 扭矩关）。"""
    transport.send(b'{"cmd":"car_stop"}\n')


def main() -> None:
    if sys.platform != "win32":
        raise RuntimeError("键盘输入仅实现 Windows（msvcrt）")

    ap = argparse.ArgumentParser(description="三轮 kiwi 底盘无线键盘遥控")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--serial", default=None, help="USB 串口（如 COM5），走串口而非 TCP")
    args = ap.parse_args()

    transport: Transport = (
        SerialTransport(args.serial) if args.serial else TcpTransport(args.host, args.port)
    )
    link_name = f"串口 {args.serial}" if args.serial else f"TCP {args.host}:{args.port}"

    import msvcrt

    # 当前目标运动（None = 停止）。按键事件更新它；每 tick 按它持续下发。
    motion = None
    stop_reason = RemoteStop.QUIT
    last_tick = 0.0

    print(f"[car_remote] 已连接 {link_name}（20Hz 持续下发）")
    print("W/S前后 A/D横移 Z/X旋转 空格停 E急停 Q退出 —— 车体抬空首测！")
    try:
        while True:
            # 非阻塞读键：每 tick 处理一次缓冲，避免积压
            while msvcrt.kbhit():
                key = msvcrt.getch().decode("ascii", errors="ignore").lower()
                if key == "q":
                    motion = None
                    stop_reason = RemoteStop.QUIT
                    print("\n[car_remote] Q -> 退出")
                    transport.send(b'{"cmd":"car_drive","params":{"raw":[0,0,0]}}\n')
                    send_car_stop(transport)
                    return
                if key == "e":
                    motion = None
                    print("[car_remote] E -> 急停")
                    send_car_stop(transport)
                    continue
                new_motion = kiwi_drive.KEY_MOTIONS.get(key)
                if new_motion is not None:
                    motion = new_motion
                    print(f"[car_remote] {motion.value}")

            # 20Hz 持续下发当前目标（0 速度也下发：喂看门狗 + 保持刹停）
            now = time.monotonic()
            if now - last_tick >= 1.0 / TICK_HZ:
                last_tick = now
                if motion is None:
                    speeds = [0, 0, 0]
                else:
                    vx, vy, omega = kiwi_drive.MOTION_VECTORS[motion]
                    speeds = build_speeds(vx, vy, omega)
                transport.send(encode_command(speeds))

            time.sleep(0.005)
    except (ConnectionError, OSError) as exc:
        stop_reason = RemoteStop.ERROR
        print(f"\n[car_remote] 连接中断: {exc}")
    except KeyboardInterrupt:
        stop_reason = RemoteStop.QUIT
        print("\n[car_remote] Ctrl+C")
    finally:
        # 收尾：先清速刹停再关扭矩，然后断连（固件另有 500ms 看门狗兜底）
        try:
            send_car_stop(transport)
            print(f"[car_remote] 已 car_stop（{stop_reason.value}）")
        except (ConnectionError, OSError):
            pass
        transport.close()


if __name__ == "__main__":
    main()

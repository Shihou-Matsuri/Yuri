"""Camera car wired keyboard controller.

The camera car is a separate three-wheel base from the robot arm.  This entry
point talks directly to the Feetech servo bus over USB, using motor mode for
continuous wheel rotation.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import feetech

BAUD = 1_000_000
DEFAULT_PORT = "COM21"

ADDR_MODE = 0x21
ADDR_TORQUE = 0x28
ADDR_SPEED = 0x2E
MODE_MOTOR = 1

SPEED_PER_RPM = 68.0
MAX_RAW_SPEED = 1800
WRITE_SETTLE_S = 0.02


class Motion(Enum):
    STOP = "stop"
    FORWARD = "forward"
    BACKWARD = "backward"
    LEFT = "left"
    RIGHT = "right"
    ROTATE_LEFT = "rotate_left"
    ROTATE_RIGHT = "rotate_right"


@dataclass
class CarConfig:
    front_id: int = 4
    rear_left_id: int = 5
    rear_right_id: int = 6
    front_angle_deg: float = 0.0
    rear_left_angle_deg: float = 225.0
    rear_right_angle_deg: float = 135.0
    wheel_radius_m: float = 0.032
    base_radius_m: float = 0.09
    linear_speed_mps: float = 0.05
    angular_speed_rad_s: float = 0.30
    test_rpm: float = 5.0
    directions: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 2026-09-04 真机校准：ID4 前中、ID5 后左、ID6 后右；
        # 前进时后左/后右同向，后退相反。
        if not self.directions:
            self.directions = {
                self.front_id: -1,
                self.rear_left_id: -1,
                self.rear_right_id: 1,
            }

    @property
    def wheel_ids(self) -> tuple[int, int, int]:
        return (self.front_id, self.rear_left_id, self.rear_right_id)

    @property
    def wheel_angles_deg(self) -> dict[int, float]:
        return {
            self.front_id: self.front_angle_deg,
            self.rear_left_id: self.rear_left_angle_deg,
            self.rear_right_id: self.rear_right_angle_deg,
        }

    def with_directions(
        self,
        front_reversed: bool = True,
        rear_left_reversed: bool = True,
        rear_right_reversed: bool = False,
    ) -> CarConfig:
        self.directions = {
            self.front_id: -1 if front_reversed else 1,
            self.rear_left_id: -1 if rear_left_reversed else 1,
            self.rear_right_id: -1 if rear_right_reversed else 1,
        }
        return self


def print_mapping(config: CarConfig) -> None:
    def label(sign: int) -> str:
        return "反" if sign < 0 else "正"

    front = label(config.directions.get(config.front_id, 1))
    rear_left = label(config.directions.get(config.rear_left_id, 1))
    rear_right = label(config.directions.get(config.rear_right_id, 1))
    print(
        f"舵机映射: 前中=ID{config.front_id}, "
        f"后左=ID{config.rear_left_id}, 后右=ID{config.rear_right_id} | "
        f"方向: 前{front}, 后左{rear_left}, 后右{rear_right}"
    )


MOTION_VECTORS = {
    Motion.STOP: (0.0, 0.0, 0.0),
    # 该车当前轮轴方向下，前进的实际车身速度需要反向 X。
    Motion.FORWARD: (-1.0, 0.0, 0.0),
    Motion.BACKWARD: (1.0, 0.0, 0.0),
    Motion.LEFT: (0.0, 1.0, 0.0),
    Motion.RIGHT: (0.0, -1.0, 0.0),
    Motion.ROTATE_LEFT: (0.0, 0.0, 1.0),
    Motion.ROTATE_RIGHT: (0.0, 0.0, -1.0),
}

KEY_MOTIONS = {
    "w": Motion.FORWARD,
    "s": Motion.BACKWARD,
    "a": Motion.LEFT,
    "d": Motion.RIGHT,
    "z": Motion.ROTATE_LEFT,
    "x": Motion.ROTATE_RIGHT,
    " ": Motion.STOP,
}


def motion_vector(motion: Motion, config: CarConfig) -> tuple[float, float, float]:
    sx, sy, sw = MOTION_VECTORS[motion]
    return (
        sx * config.linear_speed_mps,
        sy * config.linear_speed_mps,
        sw * config.angular_speed_rad_s,
    )


def wheel_rpm(config: CarConfig, vx: float, vy: float, omega: float) -> dict[int, float]:
    """Convert body velocity into the three wheel RPM values."""
    result: dict[int, float] = {}
    for servo_id, angle_deg in config.wheel_angles_deg.items():
        angle_rad = math.radians(angle_deg)
        tangential = -math.sin(angle_rad) * vx + math.cos(angle_rad) * vy
        linear = tangential + config.base_radius_m * omega
        result[servo_id] = linear * 60.0 / (2.0 * math.pi * config.wheel_radius_m)
    return result


def rpm_to_raw(rpm: float) -> int:
    value = round(rpm * SPEED_PER_RPM)
    return max(-MAX_RAW_SPEED, min(MAX_RAW_SPEED, value))


def set_wheel_rpm(ser: Any, config: CarConfig, servo_id: int, rpm: float) -> None:
    raw = rpm_to_raw(rpm) * config.directions.get(servo_id, 1)
    feetech.write_motor_speed(ser, servo_id, ADDR_SPEED, raw)


def command(ser: Any, config: CarConfig, motion: Motion) -> None:
    for servo_id, rpm in wheel_rpm(config, *motion_vector(motion, config)).items():
        set_wheel_rpm(ser, config, servo_id, rpm)


def move(
    ser: Any,
    config: CarConfig,
    vx: float,
    vy: float,
    omega: float,
) -> None:
    for servo_id, rpm in wheel_rpm(config, vx, vy, omega).items():
        set_wheel_rpm(ser, config, servo_id, rpm)


def stop(ser: Any, config: CarConfig) -> None:
    for servo_id in config.wheel_ids:
        set_wheel_rpm(ser, config, servo_id, 0.0)


def init_servo(ser: Any, servo_id: int) -> None:
    feetech.write_byte(ser, servo_id, ADDR_MODE, MODE_MOTOR)
    time.sleep(WRITE_SETTLE_S)
    feetech.write_byte(ser, servo_id, ADDR_TORQUE, 1)
    time.sleep(WRITE_SETTLE_S)


def prepare(ser: Any, config: CarConfig, *, print_status: bool = True) -> None:
    for servo_id in config.wheel_ids:
        if not feetech.ping(ser, servo_id):
            raise RuntimeError(f"舵机 ID {servo_id} 无应答")
        init_servo(ser, servo_id)
        if print_status:
            print(f"ID {servo_id} 已进入电机模式")


def scan_ids(ser: Any) -> list[int]:
    found: list[int] = []
    for servo_id in range(1, 255):
        if feetech.ping(ser, servo_id):
            found.append(servo_id)
            print(f"在线舵机：ID {servo_id}")
    return found


def open_serial(port: str, baud: int = BAUD) -> Any:
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("未安装 pyserial，请先安装后重试") from exc
    return serial.Serial(port, baud, timeout=0.1)


def list_serial_ports() -> list[str]:
    try:
        from serial.tools import list_ports

        return [item.device for item in list_ports.comports()]
    except Exception:
        return []


def close_torque(ser: Any, config: CarConfig) -> None:
    for servo_id in config.wheel_ids:
        feetech.write_byte(ser, servo_id, ADDR_TORQUE, 0)
        time.sleep(WRITE_SETTLE_S)


def one_wheel_test(
    ser: Any,
    config: CarConfig,
    servo_id: int,
    duration_s: float,
) -> None:
    if servo_id not in config.wheel_ids:
        raise ValueError(f"舵机 ID {servo_id} 不在本车配置中")
    if not feetech.ping(ser, servo_id):
        raise RuntimeError(f"舵机 ID {servo_id} 无应答")
    init_servo(ser, servo_id)
    direction = config.directions.get(servo_id, 1)
    raw = rpm_to_raw(config.test_rpm) * direction
    print(f"让 ID {servo_id} 逻辑正转 {duration_s:.1f}s（原始速度 {raw}）……")
    set_wheel_rpm(ser, config, servo_id, config.test_rpm)
    time.sleep(duration_s)
    set_wheel_rpm(ser, config, servo_id, 0.0)
    feetech.write_byte(ser, servo_id, ADDR_TORQUE, 0)
    print("测试完成，已停止并关闭扭矩")


def keyboard_loop(ser: Any, config: CarConfig) -> None:
    if sys.platform != "win32":
        raise RuntimeError("键盘控制目前仅支持 Windows（msvcrt）")

    import msvcrt

    torque_on = True
    print("W/S前后 A/D横移 Z/X旋转 空格停 E急停 Q退出")
    while True:
        if not msvcrt.kbhit():
            time.sleep(0.02)
            continue
        key = msvcrt.getch().decode("ascii", errors="ignore").lower()
        if key == "q":
            return
        if key == "e":
            stop(ser, config)
            close_torque(ser, config)
            torque_on = False
            print("急停：已停止并关闭扭矩")
            continue
        motion = KEY_MOTIONS.get(key)
        if motion is None:
            continue
        if not torque_on:
            prepare(ser, config, print_status=False)
            torque_on = True
        command(ser, config, motion)
        print(motion.value)


def shutdown(ser: Any, config: CarConfig) -> None:
    try:
        stop(ser, config)
        close_torque(ser, config)
    finally:
        ser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="有线相机小车键盘控制")
    parser.add_argument("--port", default=os.getenv("CAMERA_CAR_PORT", DEFAULT_PORT))
    parser.add_argument("--baud", type=int, default=BAUD)
    parser.add_argument("--front-id", type=int, default=4, help="前方中心舵机 ID")
    parser.add_argument("--rear-left-id", type=int, default=5, help="后方左侧舵机 ID")
    parser.add_argument("--rear-right-id", type=int, default=6, help="后方右侧舵机 ID")
    parser.add_argument(
        "--front-reversed",
        dest="front_reversed",
        action="store_true",
        default=True,
        help="前轮反向（当前默认反向）",
    )
    parser.add_argument(
        "--normal-front",
        dest="front_reversed",
        action="store_false",
        help="前轮正向（覆盖默认反向）",
    )
    parser.add_argument(
        "--normal-rear-left",
        dest="rear_left_reversed",
        action="store_false",
        default=True,
        help="后左轮正向（覆盖默认反向）",
    )
    parser.add_argument(
        "--rear-left-reversed",
        dest="rear_left_reversed",
        action="store_true",
        help="后左轮反向",
    )
    parser.add_argument(
        "--normal-rear-right",
        dest="rear_right_reversed",
        action="store_false",
        default=False,
        help="后右轮正向（当前默认正向）",
    )
    parser.add_argument(
        "--rear-right-reversed",
        dest="rear_right_reversed",
        action="store_true",
        help="后右轮反向",
    )
    parser.add_argument(
        "--front-angle",
        type=float,
        default=0.0,
        help="前方中心轮角度（度）",
    )
    parser.add_argument(
        "--rear-left-angle",
        type=float,
        default=225.0,
        help="后方左侧轮角度（度）",
    )
    parser.add_argument(
        "--rear-right-angle",
        type=float,
        default=135.0,
        help="后方右侧轮角度（度）",
    )
    parser.add_argument(
        "--wheel-radius-mm",
        type=float,
        default=32.0,
        help="车轮半径（毫米）",
    )
    parser.add_argument(
        "--base-radius-mm",
        type=float,
        default=90.0,
        help="车心到车轮中心距离（毫米）",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.05,
        help="平移速度 m/s",
    )
    parser.add_argument(
        "--angular-speed",
        type=float,
        default=0.30,
        help="自旋速度 rad/s",
    )
    parser.add_argument("--test-rpm", type=float, default=5.0)
    parser.add_argument("--scan", action="store_true", help="只扫描总线 ID")
    parser.add_argument("--check", action="store_true", help="只检查 4/5/6 是否在线")
    parser.add_argument(
        "--one-wheel",
        type=int,
        default=None,
        metavar="ID",
        help="单轮低速测试，先观察转向再落地",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.8,
        help="单轮测试时长（秒）",
    )
    parser.add_argument("--mock", action="store_true", help="不连接硬件，只做逻辑验证")
    return parser.parse_args()


class FakeSerial:
    def __init__(self) -> None:
        self.packets: list[bytes] = []
        self._ping_response = b"\xff\xff\x04\x02\x00\xfa"

    def write(self, data: bytes) -> int:
        self.packets.append(data)
        return len(data)

    def flush(self) -> None:
        return None

    def reset_input_buffer(self) -> None:
        return None

    def read(self, size: int) -> bytes:
        if size >= 6:
            return self._ping_response[:size]
        return b""

    def close(self) -> None:
        return None


def main() -> int:
    args = parse_args()
    config = CarConfig(
        front_id=args.front_id,
        rear_left_id=args.rear_left_id,
        rear_right_id=args.rear_right_id,
        front_angle_deg=args.front_angle,
        rear_left_angle_deg=args.rear_left_angle,
        rear_right_angle_deg=args.rear_right_angle,
        wheel_radius_m=args.wheel_radius_mm / 1000.0,
        base_radius_m=args.base_radius_mm / 1000.0,
        linear_speed_mps=args.speed,
        angular_speed_rad_s=args.angular_speed,
        test_rpm=args.test_rpm,
    ).with_directions(
        front_reversed=args.front_reversed,
        rear_left_reversed=args.rear_left_reversed,
        rear_right_reversed=args.rear_right_reversed,
    )
    print_mapping(config)

    if args.mock:
        serial = FakeSerial()
        prepare(serial, config)
        command(serial, config, Motion.FORWARD)
        print(f"mock 已发送 {len(serial.packets)} 个数据包")
        return 0

    ser = open_serial(args.port, args.baud)
    try:
        if args.scan:
            found = scan_ids(ser)
            print(f"共发现 {len(found)} 个在线舵机：{found}")
            return 0
        if args.check:
            missing = []
            for servo_id in config.wheel_ids:
                if not feetech.ping(ser, servo_id):
                    missing.append(servo_id)
            if missing:
                print(f"缺少在线舵机：{missing}")
                return 1
            print("4/5/6 在线")
            return 0
        if args.one_wheel is not None:
            one_wheel_test(ser, config, args.one_wheel, args.duration)
            return 0
        prepare(ser, config)
        keyboard_loop(ser, config)
        return 0
    finally:
        if not args.scan and not args.check:
            shutdown(ser, config)
        else:
            ser.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""三轮 Kiwi 全向底盘底层控制。

适用硬件：
- 3 × STS3215 12V（电机恒速模式）
- 官方 LeKiwi 三轮 120°布局
- USB→URT-1 / 飞特舵机控制板

运行前：车体抬空，逐轮以 TEST_RPM 测试方向；确认后再放地。
"""
import math
import sys
import time
from enum import Enum

import feetech

# ---------- 串口与舵机 ----------
BAUD = 1000000
PORT = "COM5"

ID_LEFT = 7
ID_BACK = 8
ID_RIGHT = 9
WHEEL_IDS = (ID_LEFT, ID_BACK, ID_RIGHT)
ADDR_MODE = 0x21
ADDR_TORQUE = 0x28
ADDR_SPEED = 0x2E
MODE_MOTOR = 1

# ---------- 车体几何 ----------
WHEEL_RADIUS_M = 0.0507845  # 官方4in轮实测外径101.569mm / 2
BASE_RADIUS_M = 0.123       # 待最终装配后实测：圆心到轮接地点

# 车体坐标：+X前方，+Y左方（车头朝上、左=左手边）。
# 由用户单轮实测(正转时整车滑向)自动反解出真实驱动方位角：
#   ID7 左前 → 车滑向 后左 → θ = 45°
#   ID8 后轮 → 车滑向 右   → θ = 180°
#   ID9 右前 → 车滑向 前左 → θ = 315°
# 反解公式：单位向量(tx,ty)，θ = atan2(-tx, ty)。
WHEEL_ANGLES_DEG = {
    ID_LEFT: 45.0,    # ID7 左前
    ID_BACK: 180.0,   # ID8 后轮
    ID_RIGHT: 315.0,  # ID9 右前
}

# 前进测试中某轮物理装反时，只把对应值改为 -1。
# 默认全 1：假设按官方 LeKiwi 对称装配。某轮实际反向才改它。
DIRECTION = {
    ID_LEFT: 1,
    ID_BACK: 1,
    ID_RIGHT: 1,
}

# ---------- STS3215 速度 ----------
SPEED_PER_RPM = 68.
MAX_RAW_SPEED = 1800
TEST_RPM = 5.0
LINEAR_SPEED_MPS = 0.10
ANGULAR_SPEED_RAD_S = 0.60


class Motion(Enum):
    STOP = "stop"
    FORWARD = "forward"
    BACKWARD = "backward"
    LEFT = "left"
    RIGHT = "right"
    ROTATE_LEFT = "rotate_left"
    ROTATE_RIGHT = "rotate_right"


MOTION_VECTORS = {
    Motion.STOP: (0.0, 0.0, 0.0),
    Motion.FORWARD: (LINEAR_SPEED_MPS, 0.0, 0.0),
    Motion.BACKWARD: (-LINEAR_SPEED_MPS, 0.0, 0.0),
    Motion.LEFT: (0.0, LINEAR_SPEED_MPS, 0.0),
    Motion.RIGHT: (0.0, -LINEAR_SPEED_MPS, 0.0),
    Motion.ROTATE_LEFT: (0.0, 0.0, ANGULAR_SPEED_RAD_S),
    Motion.ROTATE_RIGHT: (0.0, 0.0, -ANGULAR_SPEED_RAD_S),
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


def wheel_rpm(vx: float, vy: float, omega: float) -> dict[int, float]:
    """车体速度 vx/vy/omega 转为三轮目标 RPM。"""
    result = {}

    for servo_id, angle_deg in WHEEL_ANGLES_DEG.items():
        angle_rad = math.radians(angle_deg)
        tangential_speed = -math.sin(angle_rad) * vx + math.cos(angle_rad) * vy
        wheel_linear_speed = tangential_speed + BASE_RADIUS_M * omega
        rpm = wheel_linear_speed * 60.0 / (2.0 * math.pi * WHEEL_RADIUS_M)
        result[servo_id] = rpm

    return result


def reconstruct_body_speed(wheel_rpms: dict[int, float]) -> tuple[float, float, float]:
    """从三个轮速(RPM)反解车体速度 (vx, vy, omega)。

    与 wheel_rpm 互逆。用于测试验证运动学正确性（纯平移输入应得到
    重建角速度≈0），也可扩展用于读取编码器反馈。

    求解 3×3 线性系统（高斯消元）：
        w_i_lin = -sin(θ_i)·vx + cos(θ_i)·vy + R·omega
    其中 w_i_lin 是轮子线速度(m/s)，需先把 RPM 换算：lin = rpm·2π·r/60。
    """
    ids = WHEEL_IDS
    lin_scale = 2.0 * math.pi * WHEEL_RADIUS_M / 60.0
    mat = []
    for sid in ids:
        theta = math.radians(WHEEL_ANGLES_DEG[sid])
        mat.append([
            -math.sin(theta),
            math.cos(theta),
            BASE_RADIUS_M,
        ])
    rhs = [wheel_rpms[sid] * lin_scale for sid in ids]

    # 高斯消元解 3×3
    aug = [row + [rhs[i]] for i, row in enumerate(mat)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        if abs(aug[col][col]) < 1e-12:
            raise ValueError("轮子方位角退化，无法反解")
        for r in range(3):
            if r != col:
                factor = aug[r][col] / aug[col][col]
                for c in range(col, 4):
                    aug[r][c] -= factor * aug[col][c]
    solution = [aug[i][3] / aug[i][i] for i in range(3)]
    return solution[0], solution[1], solution[2]


def rpm_to_raw(rpm: float) -> int:
    """RPM 转 STS3215 有符号原始速度，并施加安全上限。"""
    raw_speed = round(rpm * SPEED_PER_RPM)
    return max(-MAX_RAW_SPEED, min(MAX_RAW_SPEED, raw_speed))


def set_wheel_rpm(ser, servo_id: int, rpm: float) -> None:
    """设置一只轮子的转速。

    用 write_motor_speed 走 BIT15 幅值编码：确保正/反转转速对称，
    修复之前 write_word 补码编码导致的反向满速、左右转速不一致问题。
    """
    raw_speed = rpm_to_raw(rpm) * DIRECTION[servo_id]
    feetech.write_motor_speed(ser, servo_id, ADDR_SPEED, raw_speed)


def move(ser, vx: float, vy: float, omega: float) -> None:
    """执行全向运动。"""
    for servo_id, rpm in wheel_rpm(vx, vy, omega).items():
        set_wheel_rpm(ser, servo_id, rpm)


def command(ser, motion: Motion) -> None:
    """执行一个预定义运动。"""
    move(ser, *MOTION_VECTORS[motion])


def stop(ser) -> None:
    """三轮立即停止。"""
    command(ser, Motion.STOP)


def init_servo(ser, servo_id: int) -> None:
    """切换一台 STS3215 到电机模式并启用扭矩。"""
    feetech.write_byte(ser, servo_id, ADDR_MODE, MODE_MOTOR)
    feetech.write_byte(ser, servo_id, ADDR_TORQUE, 1)


def find_port() -> str | None:
    """自动找第一个可用串口。"""
    from serial.tools import list_ports

    ports = [item.device for item in list_ports.comports()]
    return ports[0] if ports else None


def open_serial():
    """建立到 URT-1 的串口连接。"""
    port = PORT or find_port()
    if port is None:
        raise RuntimeError("找不到串口：请插 URT-1，或在 PORT 中填写 COM 口")

    import serial

    connection = serial.Serial(port, BAUD, timeout=0.2)
    print(f"已连接 {port} @ {BAUD}")
    return connection


def prepare(ser) -> None:
    """检查三台底盘舵机，并进入电机模式。"""
    for servo_id in WHEEL_IDS:
        if not feetech.ping(ser, servo_id):
            raise RuntimeError(f"舵机 ID {servo_id} 无应答")
        init_servo(ser, servo_id)
        print(f"ID {servo_id} 已进入电机模式")


def test_one_wheel(ser, servo_id: int) -> None:
    """低速点动单轮，用于确认真实安装方向。"""
    stop(ser)
    set_wheel_rpm(ser, servo_id, TEST_RPM)
    time.sleep(0.8)
    stop(ser)


def shutdown(ser) -> None:
    """停止、关闭扭矩、释放串口。"""
    stop(ser)
    for servo_id in WHEEL_IDS:
        feetech.write_byte(ser, servo_id, ADDR_TORQUE, 0)
    ser.close()


def keyboard_loop(ser) -> None:
    """Windows 键盘控制：W/S前后，A/D横移，Z/X旋转，空格停，Q退出。"""
    if sys.platform != "win32":
        raise RuntimeError("当前初版键盘输入仅实现 Windows")

    import msvcrt

    print("W/S前后 A/D横移 Z/X旋转 空格停 Q退出")
    while True:
        if not msvcrt.kbhit():
            time.sleep(0.02)
            continue

        key = msvcrt.getch().decode("ascii", errors="ignore").lower()
        if key == "q":
            return
        motion = KEY_MOTIONS.get(key)
        if motion is not None:
            command(ser, motion)
            print(motion.value)


def main() -> None:
    ser = open_serial()
    try:
        prepare(ser)
        keyboard_loop(ser)
    finally:
        shutdown(ser)


if __name__ == "__main__":
    main()

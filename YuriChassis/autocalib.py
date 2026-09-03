"""三轮全向自动标定：按提示看车动，自动写出正确方位角。

用法：
1. 车放地上（要能观察整车滑动方向）。
2. 运行本脚本。确认车头方向（默认前方=屏幕上方/远离你，即你按W时想去的那边）。
3. 脚本会依次让 ID7、ID8、ID9 正转，每次你输入"车往哪个方向滑"。
4. 三个都输完，脚本算出真实驱动方位角，写入 kiwi_drive.py。
"""

import math
import sys
import time
from pathlib import Path

import serial

import feetech

PORT = "COM5"
BAUD = 1000000

ADDR_MODE = 0x21
ADDR_TORQUE = 0x28
ADDR_SPEED = 0x2E
MODE_MOTOR = 1

TEST_SPEED = 400
ID_ORDER = (7, 8, 9)

# 8方位 → 车体坐标系单位向量。+X=前方，+Y=左方。
DIRECTION_VEC = {
    "前": (1.0, 0.0),
    "前右": (0.707, -0.707),
    "右": (0.0, -1.0),
    "后右": (-0.707, -0.707),
    "后": (-1.0, 0.0),
    "后左": (-0.707, 0.707),
    "左": (0.0, 1.0),
    "前左": (0.707, 0.707),
}


def angle_from_vec(tx, ty):
    """把单位向量 (tx,ty) 转成代码用的方位角 θ。
    代码里 tangential = -sin(θ)*vx + cos(θ)*vy，即 t=(-sinθ, cosθ)。
    所以 sinθ = -tx, cosθ = ty → θ = atan2(-tx, ty)。
    """
    theta = math.atan2(-tx, ty)
    return (math.degrees(theta) % 360)


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.2)
    print(f"已连接 {PORT} @ {BAUD}\n")

    for sid in ID_ORDER:
        if not feetech.ping(ser, sid):
            print(f"⚠ 舵机 ID {sid} 无应答，跳过")
            return
        feetech.write_byte(ser, sid, ADDR_MODE, MODE_MOTOR)
        feetech.write_byte(ser, sid, ADDR_TORQUE, 1)

    print("=== 三轮全向自动标定 ===\n")
    print("车头方向确认：正前方 = 你按 W 想去的方向（=你的正前方）")
    print("输入车滑向 → 用：前/前左/左/后左/后/后右/右/前右\n")
    print("选项说明（你的视角）：前=朝车头去，后=朝车尾，左=你的左手边，右=你的右手边")

    angles = {}
    for sid in ID_ORDER:
        name = {7: "左前", 8: "后轮", 9: "右前"}[sid]
        # 先全停
        for other in ID_ORDER:
            feetech.write_word(ser, other, ADDR_SPEED, 0)
        time.sleep(0.5)

        print(f"\n▶ 正在让ID {sid}({name}) 正转... 看整车往哪个方向滑")
        feetech.write_word(ser, sid, ADDR_SPEED, TEST_SPEED)
        time.sleep(2.0)
        feetech.write_word(ser, sid, ADDR_SPEED, 0)

        while True:
            ans = input(f"    ID {sid} 正转，车往哪滑？(输方向词) > ").strip().lower()
            if ans in DIRECTION_VEC:
                tx, ty = DIRECTION_VEC[ans]
                angles[sid] = angle_from_vec(tx, ty)
                break
            print("    请输：前/前左/左/后左/后/后右/右/前右")

    print("\n=== 标定结果 ===")
    for sid in ID_ORDER:
        print(f"  ID {sid}  → 方位角 {angles[sid]:.1f}°")

    # 写入 kiwi_drive.py
    target = Path(__file__).resolve().parent / "kiwi_drive.py"
    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    out_lines = []
    for line in lines:
        out_lines.append(line)
    # 找到 WHEEL_ANGLES_DEG 那段替换（简单按行定位）
    new_block = [
        "WHEEL_ANGLES_DEG = {",
        f"    ID_LEFT: {angles[7]:.1f},   # ID7 左前 (自动标定)",
        f"    ID_BACK: {angles[8]:.1f},   # ID8 后轮 (自动标定)",
        f"    ID_RIGHT: {angles[9]:.1f},  # ID9 右前 (自动标定)",
        "}",
    ]
    start = None
    end = None
    for i, line in enumerate(lines):
        if "WHEEL_ANGLES_DEG = {" in line:
            start = i
        if start is not None and line.strip() == "}":
            end = i
            break
    if start is not None and end is not None:
        text = "\n".join(lines[:start] + new_block + lines[end + 1:])
        target.write_text(text, encoding="utf-8")
        print("\n✅ 已写入 kiwi_drive.py 的 WHEEL_ANGLES_DEG")

    for sid in ID_ORDER:
        feetech.write_byte(ser, sid, ADDR_TORQUE, 0)
    ser.close()
    print("\n标定完成，已释放串口。可立即运行 kiwi_drive.py 测试。")


if __name__ == "__main__":
    main()

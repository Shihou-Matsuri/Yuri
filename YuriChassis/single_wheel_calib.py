"""单轮标定：一次只让一个轮子转，观察车体往哪个方向移动。

方法（最可靠，不再靠"看轮子转"）：
1. 把车放【地上】，别悬空（要看车体真的往哪滑）。
2. 运行本脚本：它会依次让 ID7、ID8、ID9 各正转 2 秒，其他两个停。
3. 每转一个，看【整辆车】（底盘）往哪个方向移动：
       前 / 后 / 左 / 右 / 斜前左 / 斜前右 / 斜后左 / 斜后右
4. 记录三个轮子各自对应的移动方向。

用途：根据三个轮子"正转时车体往哪动"，可直接算出每个轮子的真实驱动方位，
一次性写对运动学，不再反复试角度。

波特率 1000000（与 kiwi_drive 一致）。
"""
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

ser = serial.Serial(PORT, BAUD, timeout=0.2)
print(f"已连接 {PORT} @ {BAUD}\n")

# 三个进电机模式 + 扭矩
for sid in ID_ORDER:
    if not feetech.ping(ser, sid):
        print(f"⚠ ID {sid} 无应答，跳过")
        continue
    feetech.write_byte(ser, sid, ADDR_MODE, MODE_MOTOR)
    feetech.write_byte(ser, sid, ADDR_TORQUE, 1)

print("=== 单轮标定（车放地上）===\n")
for sid in ID_ORDER:
    # 先全停
    for other in ID_ORDER:
        feetech.write_word(ser, other, ADDR_SPEED, 0)
    time.sleep(0.5)

    print(f"▶ 只给 ID {sid} 发【正速度 +{TEST_SPEED}】，看整车往哪个方向滑...")
    feetech.write_word(ser, sid, ADDR_SPEED, TEST_SPEED)
    time.sleep(2.0)
    feetech.write_word(ser, sid, ADDR_SPEED, 0)

print("\n=== 填表 ===")
print("单轮正转时整车移动方向：")
print(f"  ID{7}: 往前/后/左/右/斜向？")
print(f"  ID{8}: 往前/后/左/右/斜向？")
print(f"  ID{9}: 往前/后/左/右/斜向？")

for sid in ID_ORDER:
    feetech.write_byte(ser, sid, ADDR_TORQUE, 0)
ser.close()
print("\n已释放串口")

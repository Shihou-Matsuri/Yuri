""""方向校准 v2"：一次只让一个轮子转，确认每个轮子物理转向。

用法：
1. 把车架起来，三只轮子悬空。
2. 运行本脚本，依次让 ID 7、8、9 各正转 1.5 秒。
3. 亲眼看：
   - 发给它的速度是【正】(+speed)
   - 实际轮子往哪滚？（前滚 = 正转，后滚 = 反转）

本脚本波特率用 1000000（和 kiwi_drive.py 一致）。
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

TEST_SPEED = 500
ID_ORDER = (7, 8, 9)

ser = serial.Serial(PORT, BAUD, timeout=0.2)
print(f"已连接 {PORT} @ {BAUD}\n")

for sid in ID_ORDER:
    if not feetech.ping(ser, sid):
        print(f"⚠ ID {sid} 无应答，跳过")
        continue
    feetech.write_byte(ser, sid, ADDR_MODE, MODE_MOTOR)
    feetech.write_byte(ser, sid, ADDR_TORQUE, 1)

print("=== 逐个正转测试（悬空）===\n")
for sid in ID_ORDER:
    print(f"▶ 给 ID {sid} 发【正速度 +{TEST_SPEED}】，观察轮子滚向哪...")
    feetech.write_word(ser, sid, ADDR_SPEED, TEST_SPEED)
    time.sleep(1.5)
    feetech.write_word(ser, sid, ADDR_SPEED, 0)
    time.sleep(0.5)

print("\n=== 完 ===")
for sid in ID_ORDER:
    print(f"  ID {sid} 正转时：轮子往前滚 / 往后滚？")
for sid in ID_ORDER:
    feetech.write_byte(ser, sid, ADDR_TORQUE, 0)
ser.close()
print("已释放串口")

"""扫描总线上所有在线舵机 ID。波特率 1000000（与 kiwi_drive 一致）。"""
import sys
from pathlib import Path

import serial

import feetech

PORT = "COM5"
BAUD = 1000000

ser = serial.Serial(PORT, BAUD, timeout=0.05)
print(f"已连接 {PORT} @ {BAUD}\n")

servos = []
for servo_id in range(1, 255):
    if feetech.ping(ser, servo_id):
        servos.append(servo_id)
        print(f"    ✔ 在线舵机：ID {servo_id}")

print(f"\n共发现 {len(servos)} 个在线舵机")
if servos:
    print(f"在线 ID：{servos}")
    print("\n对照：代码需要 7(左前) 8(后) 9(右前)")
    missing = [sid for sid in (7, 8, 9) if sid not in servos]
    if missing:
        print(f"⚠ 缺少：{missing} —— 这些舵机没接上/没通电/ID不对")
    else:
        print("✅ 7/8/9 都在线，问题在别处")
ser.close()

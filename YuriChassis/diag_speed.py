"""诊断：逐个舵机正/负速，实测转速是否对称。

用法：车放地上或悬空。脚本依次给每个轮发 +800 和 -800，
打印编码字节，并提示观察。用于确认：
  1. 舵机是否响应
  2. 正/负转转速是否对称（验证 BIT15 编码是否生效）
"""
import sys
import time
from pathlib import Path

import serial

import feetech

PORT = "COM5"
BAUD = 1000000
ADDR_SPEED = 0x2E

ser = serial.Serial(PORT, BAUD, timeout=0.2)
print(f"已连接 {PORT} @ {BAUD}\n")

# 确认所有舵机在电机模式
for sid in (7, 8, 9):
    if not feetech.ping(ser, sid):
        print(f"⚠ ID {sid} 无应答！")
        continue
    feetech.write_byte(ser, sid, 0x21, 1)   # 电机模式
    feetech.write_byte(ser, sid, 0x28, 1)   # 扭矩开

print("编码验证：")
for v in (800, -800, 1279, -1279):
    print(f"  speed={v:+6d} → encode=0x{feetech.encode_motor_speed(v):04X}")

print("\n=== 逐轮正/负速实测 ===")
for sid in (7, 8, 9):
    name = {7: "左前", 8: "后轮", 9: "右前"}[sid]
    # 正速
    feetech.write_motor_speed(ser, sid, ADDR_SPEED, 800)
    print(f"\n▶ ID{sid}({name}) +800  观察转速")
    time.sleep(1.5)
    feetech.write_motor_speed(ser, sid, ADDR_SPEED, 0)
    time.sleep(0.5)
    # 负速
    feetech.write_motor_speed(ser, sid, ADDR_SPEED, -800)
    print(f"▶ ID{sid}({name}) -800  观察转速（应与+800一样快，只是反向）")
    time.sleep(1.5)
    feetech.write_motor_speed(ser, sid, ADDR_SPEED, 0)
    time.sleep(0.5)

for sid in (7, 8, 9):
    feetech.write_byte(ser, sid, 0x28, 0)
ser.close()
print("\n完成，已释放串口")

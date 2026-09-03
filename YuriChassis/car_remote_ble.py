"""三轮 kiwi 底盘 BLE 键盘遥控（经 Yuri ESP32-S3 执行端）。

链路: 笔记本 --BLE--> ESP32-S3 --UART2--> 3×STS3215（电机恒速模式）

复用同目录 kiwi_drive.py 的运动学与键位定义，以及 car_remote.py 的
car_drive 原始速度数组构造。固件需要 car_drive / car_resume / car_stop。

用法:
    python car_remote_ble.py                 # 自动扫描 YuriArm-S3
    python car_remote_ble.py --address AA:BB:CC:DD:EE:FF

按键:
    W/S 前后   A/D 横移   Z/X 旋转   空格 停   E 急停(car_stop)   Q 退出
"""
from __future__ import annotations

import argparse
import asyncio
import json
import msvcrt
import sys
import time

import kiwi_drive
from car_remote import CAR_SERVO_ORDER, build_speeds
from bleak import BleakClient, BleakScanner

BLE_RX_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
TICK_HZ = 20


def encode_drive(speeds: list[int]) -> bytes:
    """组 car_drive 指令行（raw 顺序 = CAR_SERVO_IDS 7/8/9）。"""
    payload = {"cmd": "car_drive", "params": {"raw": speeds}}
    return (json.dumps(payload) + "\n").encode("utf-8")


async def find_device(address: str | None) -> str:
    if address:
        return address
    devices = await BleakScanner.discover(timeout=8.0)
    for d in devices:
        if (d.name or "").lower().startswith("yuriarm-s3"):
            print(f"[+] 找到 {d.name}  {d.address}")
            return d.address
    raise RuntimeError("未找到 YuriArm-S3，请检查蓝牙或使用 --address")


async def run_remote(address: str | None) -> None:
    addr = await find_device(address)
    print(f"[*] 连接 {addr} ...")

    async with BleakClient(addr, timeout=15.0) as client:
        print("[+] 已连接")
        # 清除上次可能遗留的 car_stop 急停；后续按键 E 会再次停住。
        await client.write_gatt_char(BLE_RX_UUID, b'{"cmd":"car_resume"}\n')
        print("W/S前后 A/D横移 Z/X旋转 空格停 E急停 Q退出 —— 车体抬空首测！")

        motion = None
        estop_active = False
        last_tick = 0.0

        try:
            while True:
                while msvcrt.kbhit():
                    key = msvcrt.getch().decode("ascii", errors="ignore").lower()
                    if key == "q":
                        motion = None
                        print("\n[+] Q -> 退出")
                        await client.write_gatt_char(BLE_RX_UUID, encode_drive([0, 0, 0]))
                        await client.write_gatt_char(BLE_RX_UUID, b'{"cmd":"car_stop"}\n')
                        return
                    if key == "e":
                        motion = None
                        estop_active = True
                        print("[+] E -> 急停")
                        await client.write_gatt_char(BLE_RX_UUID, b'{"cmd":"car_stop"}\n')
                        continue

                    new_motion = kiwi_drive.KEY_MOTIONS.get(key)
                    if new_motion is not None:
                        if estop_active:
                            await client.write_gatt_char(BLE_RX_UUID, b'{"cmd":"car_resume"}\n')
                            estop_active = False
                        motion = new_motion
                        print(f"[+] {motion.value}")

                now = time.monotonic()
                if now - last_tick >= 1.0 / TICK_HZ:
                    last_tick = now
                    if motion is None:
                        speeds = [0, 0, 0]
                    else:
                        speeds = build_speeds(*kiwi_drive.MOTION_VECTORS[motion])
                    await client.write_gatt_char(BLE_RX_UUID, encode_drive(speeds))
                await asyncio.sleep(0.005)
        finally:
            try:
                await client.write_gatt_char(BLE_RX_UUID, encode_drive([0, 0, 0]))
                await client.write_gatt_char(BLE_RX_UUID, b'{"cmd":"car_stop"}\n')
                print("[+] 已 car_stop")
            except Exception:
                pass


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("键盘输入仅实现 Windows（msvcrt）")

    ap = argparse.ArgumentParser(description="三轮 kiwi 底盘 BLE 键盘遥控")
    ap.add_argument("--address", default=None, help="BLE MAC（跳过扫描）")
    args = ap.parse_args()
    try:
        asyncio.run(run_remote(args.address))
    except KeyboardInterrupt:
        print("\n[+] Ctrl+C")
    except Exception as exc:
        print(f"[-] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

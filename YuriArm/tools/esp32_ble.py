"""ESP32-S3 BLE 指令通道测试（PC 需有蓝牙，已 pip install bleak）。

用法:
    python tools/esp32_ble.py                      # ping
    python tools/esp32_ble.py --status
    python tools/esp32_ble.py --telemetry
    python tools/esp32_ble.py --move '{"shoulder_lift":30}' --duration 2
    python tools/esp32_ble.py --estop
    python tools/esp32_ble.py --address AA:BB:CC:DD:EE:FF --cmd telemetry   # 直连指定 MAC
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from bleak import BleakClient, BleakScanner

BLE_RX_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
BLE_TX_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"


async def find_device(address: str | None, name_hint: str = "YuriArm") -> str | None:
    if address:
        return address
    print("[*] 扫描 BLE 设备 ...")
    devices = await BleakScanner.discover(timeout=8.0)
    for d in devices:
        n = d.name or ""
        if name_hint.lower() in n.lower():
            print(f"[+] 找到 {n}  {d.address}")
            return d.address
    print("[-] 未找到目标，附近 BLE 设备：")
    for d in devices[:20]:
        print(f"    {d.name or '(无名称)'}  {d.address}")
    return None


async def send_cmd(client, queue, cmd: str, params: dict | None = None, cid: int = 1, timeout: float = 8.0) -> dict:
    msg = {"id": cid, "cmd": cmd, "params": params or {}}
    await client.write_gatt_char(BLE_RX_UUID, (json.dumps(msg) + "\n").encode("utf-8"))
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return {"ok": False, "error": "BLE 响应超时"}
        try:
            r = await asyncio.wait_for(queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return {"ok": False, "error": "BLE 响应超时"}
        if not isinstance(r, dict):
            continue
        if r.get("id") == cid or "id" not in r:
            return r  # 忽略心跳 ping 的回复


async def main() -> int:
    ap = argparse.ArgumentParser(description="ESP32-S3 BLE 指令通道测试")
    ap.add_argument("--address", default=None, help="BLE MAC（跳过扫描）")
    ap.add_argument("--cmd", default="ping")
    ap.add_argument("--params", default=None, help='JSON 参数')
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--telemetry", action="store_true")
    ap.add_argument("--move", default=None, help='move_joints targets JSON')
    ap.add_argument("--duration", type=float, default=2.0)
    ap.add_argument("--estop", action="store_true")
    args = ap.parse_args()

    addr = await find_device(args.address)
    if not addr:
        return 1

    print(f"[*] 连接 {addr} ...")
    queue: asyncio.Queue = asyncio.Queue()
    rx_buf = bytearray()

    async with BleakClient(addr, timeout=15.0) as client:
        print("[+] 已连接")

        def on_notify(_c, data):
            # 固件按 20 字节分片发送、以 '\n' 分帧，这里重组完整 JSON 行
            rx_buf.extend(data)
            while b"\n" in rx_buf:
                line, _, rest = rx_buf.partition(b"\n")
                del rx_buf[:]
                rx_buf.extend(rest)
                line = line.strip()
                if not line:
                    continue
                try:
                    queue.put_nowait(json.loads(line.decode("utf-8")))
                except json.JSONDecodeError:
                    pass  # 丢弃不完整/非 JSON 分片

        await client.start_notify(BLE_TX_UUID, on_notify)

        hb_stop = asyncio.Event()

        async def heartbeat():
            cid = 900
            while not hb_stop.is_set():
                try:
                    await client.write_gatt_char(
                        BLE_RX_UUID, (json.dumps({"id": cid, "cmd": "heartbeat", "params": {}}) + "\n").encode("utf-8"))
                except Exception:
                    break
                cid += 1
                try:
                    await asyncio.wait_for(hb_stop.wait(), timeout=0.05)
                except asyncio.TimeoutError:
                    pass

        hb_task = asyncio.create_task(heartbeat())

        cmd = args.cmd
        params = json.loads(args.params) if args.params else {}
        if args.status:
            cmd, params = "status", {}
        elif args.telemetry:
            cmd, params = "telemetry", {}
        elif args.move:
            cmd = "move_joints"
            params = {"targets": json.loads(args.move), "duration": args.duration}
        elif args.estop:
            cmd, params = "estop", {}

        r = await send_cmd(client, queue, cmd, params)
        print(f"[{cmd}]", json.dumps(r, ensure_ascii=False, indent=2))

        if args.move:
            await asyncio.sleep(args.duration + 1.0)
            r2 = await send_cmd(client, queue, "telemetry", {}, cid=2)
            print("[telemetry]", json.dumps(r2, ensure_ascii=False, indent=2))

        if hb_task is not None:
            hb_stop.set()
            try:
                await asyncio.wait_for(hb_task, timeout=1.0)
            except asyncio.TimeoutError:
                hb_task.cancel()
        return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))








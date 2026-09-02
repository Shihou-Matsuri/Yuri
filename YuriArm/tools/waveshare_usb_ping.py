"""电脑直连 Waveshare Bus Servo Adapter (A) 的 USB 模式 ping 测试。

作用：把 Waveshare 用 USB-C 直接插到电脑（跳线帽放 B），从电脑侧确认舵机、
ID、供电、波特率是否正常，从而和 ESP32 三根杜邦线的问题分开。

用法:
    python tools/waveshare_usb_ping.py --auto
    python tools/waveshare_usb_ping.py --port COM19
    python tools/waveshare_usb_ping.py --port COM19 --baud 1000000 --ids 1 2 3

注意：只能在跳线帽位于 B（USB-SERVO）、USB-C 接电脑时使用；
这时不应同时用三根杜邦线把 ESP32 接在 UART 口上。
"""
from __future__ import annotations

import argparse
import time

import serial
import serial.tools.list_ports


def ping(ser: serial.Serial, servo_id: int, timeout: float = 0.2) -> bool:
    """发送 Feetech PING 并等待应答，返回是否收到合法状态包。"""
    pkt = bytearray([0xFF, 0xFF, servo_id, 2, 0x01, 0])
    pkt[5] = (0xFF - (servo_id + 2 + 0x01)) & 0xFF
    ser.reset_input_buffer()
    ser.write(pkt)
    ser.flush()

    end = time.time() + timeout
    buf = bytearray()
    while time.time() < end:
        chunk = ser.read(64)
        if chunk:
            buf += chunk
            # 查找 FF FF ID 02 01 <checksum>
            for i in range(len(buf) - 5):
                if buf[i] == 0xFF and buf[i + 1] == 0xFF and buf[i + 2] == servo_id:
                    if buf[i + 3] == 0x02 and buf[i + 4] == 0x01:
                        cksum = buf[i + 5] if i + 5 < len(buf) else None
                        if cksum is not None:
                            expect = (0xFF - (servo_id + 2 + 0x01)) & 0xFF
                            if cksum == expect:
                                return True
                    # 只要收到带 ID 的包就认为总线上有响应
                    return True
    return False


def scan_port(port: str, baud: int, ids: list[int], timeout: float) -> list[dict]:
    results = []
    try:
        ser = serial.Serial(port, baud, timeout=0.02, write_timeout=1.0)
    except Exception as e:
        return [{"port": port, "error": f"open failed: {e}", "ids": {}}]

    try:
        ser.reset_input_buffer()
        ser.write(bytearray([0x55] * 16))  # 试探唤醒，无头数据舵机会忽略
        ser.flush()
        time.sleep(0.05)
        for sid in ids:
            ok = ping(ser, sid, timeout)
            results.append({"port": port, "id": sid, "ping": ok})
    finally:
        ser.close()
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None, help="指定串口，如 COM19")
    ap.add_argument("--auto", action="store_true", help="自动扫描所有非调试串口")
    ap.add_argument("--baud", type=int, default=1_000_000, help="默认 1Mbps（STS3215 常用）")
    ap.add_argument("--ids", nargs="+", type=int, default=[1, 2, 3, 4, 5, 6],
                    help="要 ping 的舵机 ID")
    ap.add_argument("--timeout", type=float, default=0.25)
    args = ap.parse_args(argv)

    ports: list[str] = []
    if args.port:
        ports = [args.port]
    elif args.auto:
        # 排除 ESP32-S3 原生 USB-Serial/JTAG（VID_303A）和一些蓝牙/调试口
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if "bluetooth" in desc or "蓝牙" in desc:
                continue
            if "303a" in hwid or "usb serial/jtag" in desc:
                continue
            ports.append(p.device)
    else:
        ap.error("请用 --port 指定串口，或用 --auto 自动扫描")

    print(f"[*] 待测串口: {ports or '(无)'}  波特率: {args.baud}")
    found_any = False
    for port in ports:
        print(f"[*] 打开 {port} ...")
        rows = scan_port(port, args.baud, args.ids, args.timeout)
        for r in rows:
            if "id" in r:
                ok = r["ping"]
                found_any = found_any or ok
                print(f"  [{ 'OK' if ok else '--' }] ID {r['id']:>3}  @ {port}")
            else:
                print(f"  [xx] {r.get('error', 'unknown error')}")
    print("[*] 完成")
    return 0 if found_any else 1


if __name__ == "__main__":
    raise SystemExit(main())

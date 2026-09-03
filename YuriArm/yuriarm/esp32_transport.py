"""ESP32-S3 传输层：主动臂遥控从动臂时，把 move_joints 目标发给无线执行端。

只负责发送 JSON 行、解析一行 JSON 响应，不做协议语义（协议见 firmware/protocol.md）。

支持三种传输，接口统一（send/recv/close），与 YuriChassis/car_remote.py 的
Transport 思路一致，但加上了"读回响应"，因为 move_joints 需要确认 ESP32 收妥。

链路:
    笔记本(leader_bridge) --[WiFi TCP | BLE | USB UART0]--> ESP32-S3 --UART1--> 从动臂
"""

from __future__ import annotations

import abc
import json
import socket
import time
from typing import Any

# ---- BLE ----
BLE_RX_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"  # PC -> ESP32
BLE_TX_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"  # ESP32 -> PC


class Esp32TransportError(RuntimeError):
    """传输层错误（连不上 / 发送失败 / 读响应超时）。"""


class Esp32Transport(abc.ABC):
    """传输抽象。send 发一条 JSON 行；recv_line 读一条 JSON 响应行。"""

    name: str = "abstract"

    @abc.abstractmethod
    def send(self, obj: dict[str, Any]) -> None:
        """发送一个 dict 为 JSON 行。"""

    @abc.abstractmethod
    def recv(self, timeout_s: float) -> dict[str, Any] | None:
        """读一条 JSON 响应；超时返回 None。"""

    @abc.abstractmethod
    def close(self) -> None: ...


class TcpEsp32Transport(Esp32Transport):
    """WiFi TCP：ESP32-S3 AP，默认 192.168.4.1:8765。"""

    name = "tcp"

    def __init__(self, host: str = "192.168.4.1", port: int = 8765, timeout_s: float = 3.0):
        self._host = host
        self._port = port
        try:
            self._sock = socket.create_connection((host, port), timeout=timeout_s)
            self._sock.settimeout(timeout_s)
        except OSError as e:
            raise Esp32TransportError(
                f"无法连接 ESP32 TCP {host}:{port}（检查是否连上 {host} AP）"
            ) from e
        self._buf = b""

    def send(self, obj: dict[str, Any]) -> None:
        data = (json.dumps(obj) + "\n").encode("utf-8")
        try:
            self._sock.sendall(data)
        except OSError as e:
            raise Esp32TransportError(f"TCP 发送失败: {e}") from e

    def recv(self, timeout_s: float) -> dict[str, Any] | None:
        self._sock.settimeout(timeout_s)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if b"\n" in self._buf:
                line, _, self._buf = self._buf.partition(b"\n")
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue  # 丢弃不完整/非 JSON 行，继续等
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    raise Esp32TransportError("TCP 连接被对端关闭")
                self._buf += chunk
            except socket.timeout:
                return None
            except OSError as e:
                raise Esp32TransportError(f"TCP 读取失败: {e}") from e
        return None

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


class SerialEsp32Transport(Esp32Transport):
    """USB UART0（ESP32 板载 CH343/调试口）。波特率 115200（指令口，非舵机 1M）。"""

    name = "serial"

    def __init__(self, port: str, baud: int = 115200, timeout_s: float = 0.5):
        import serial  # 惰性导入（仅真机路径需要）

        self._timeout_s = timeout_s
        try:
            self._ser = serial.Serial(port, baud, timeout=timeout_s)
        except Exception as e:  # noqa: BLE001 —— pyserial 抛多种异常
            raise Esp32TransportError(f"无法打开串口 {port} @ {baud}: {e}") from e
        self._buf = b""

    def send(self, obj: dict[str, Any]) -> None:
        data = (json.dumps(obj) + "\n").encode("utf-8")
        try:
            self._ser.write(data)
        except Exception as e:  # noqa: BLE001
            raise Esp32TransportError(f"串口发送失败: {e}") from e

    def recv(self, timeout_s: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if b"\n" in self._buf:
                line, _, self._buf = self._buf.partition(b"\n")
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
            try:
                self._buf += self._ser.read(self._ser.in_waiting or 1)
            except Exception:  # noqa: BLE001
                return None
        return None

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:  # noqa: BLE001
            pass


class BleEsp32Transport(Esp32Transport):
    """BLE：自动扫描 YuriArm-S3 并连接，需 bleak（PC 有蓝牙）。

    ESP32 单条通知受 MTU 限制，固件按 20 字节分片发送、以 '\\n' 分帧；
    这里持续监听并重组完整 JSON 行（参考 tools/esp32_ble.py）。
    """

    name = "ble"

    def __init__(self, address: str | None = None, timeout_s: float = 15.0):
        from bleak import BleakClient, BleakScanner  # 惰性导入

        self._address = address
        self._timeout_s = timeout_s
        if self._address is None:
            devices = BleakScanner.discover(timeout=8.0)
            for d in devices:
                if (d.name or "").lower().startswith("yuriarm-s3"):
                    self._address = d.address
                    break
            if self._address is None:
                raise Esp32TransportError("未找到 YuriArm-S3 BLE 设备")
        self._client = BleakClient(self._address, timeout=self._timeout_s)

    async def _connect_and_loop(self):  # pragma: no cover —— 需真机 BLE
        raise NotImplementedError(
            "BLE 传输需异步驱动，请用 tools/leader_remote.py --link ble（asyncio）"
        )

    # BleakClient 是异步；为统一同步接口，BLE 传输在 leader_remote 里单独异步实现，
    # 本类只做同步占位与扫描，实际异步收发见 leader_bridge.run_ble()。
    def send(self, obj):  # pragma: no cover
        raise NotImplementedError("BLE 走异步路径，见 leader_bridge")

    def recv(self, timeout_s=1.0):  # pragma: no cover
        return None

    def close(self) -> None:  # pragma: no cover
        pass


def make_transport(link: str, **kwargs: Any) -> Esp32Transport:
    """工厂：link = tcp | serial | ble。"""
    link = link.lower()
    if link == "tcp":
        return TcpEsp32Transport(**kwargs)
    if link == "serial":
        return SerialEsp32Transport(**kwargs)
    raise ValueError(f"不支持的 link '{link}'（可选: tcp / serial / ble）")

"""有线相机小车（CameraCar）控制核心。

独立于 ESP32 无线链路：USB 直连 Feetech 舵机总线（默认 COM21 @1M，
三轮 ID5 前中 / ID6 后左 / ID4 后右），复用 YuriChassis/camera_car_drive
的运动学与 feetech 协议（电机恒速模式）。单写者：独立 writer 线程独占该串口。

语义（与 camera_car_drive 一致）：按住发车、无目标写 0 速刹停；E = 0 速 + 扭矩关；
扭矩关后按方向自动重新 prepare（重开扭矩）。
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_YURICHASSIS = _HERE.parents[2] / "YuriChassis"
if str(_YURICHASSIS) not in sys.path:
    sys.path.insert(0, str(_YURICHASSIS))

import camera_car_drive as cc  # noqa: E402

TICK_HZ = 20.0
SEND_PERIOD = 1.0 / TICK_HZ


class WiredCarCore:
    """有线相机小车状态与指令。发送只在 writer 线程（单写者）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.ser = None
        self.config = cc.CarConfig()
        self.port = cc.DEFAULT_PORT
        self.connected = False
        self.torque_on = False
        self.motion = None          # cc.Motion 或 None
        self._stop = threading.Event()
        self._thread = None
        self._last_tick = 0.0
        self._error = None

    # ------------------------------------------------------------ 连接
    def connect(self, port: str | None = None) -> str:
        with self._lock:
            if self.connected:
                return "already connected"
            port = (port or self.port or cc.DEFAULT_PORT).strip()
            try:
                ser = cc.open_serial(port)
                cc.prepare(ser, self.config, print_status=False)
            except Exception as exc:
                self._error = str(exc)
                return f"error: {exc}"
            self.ser = ser
            self.port = port
            self.connected = True
            self.torque_on = True
            self.motion = None
            self._start()
            return "ok"

    def disconnect(self) -> None:
        with self._lock:
            self._stop_loop()
            if self.ser is not None:
                try:
                    cc.shutdown(self.ser, self.config)
                except Exception:
                    try:
                        self.ser.close()
                    except Exception:
                        pass
            self.ser = None
            self.connected = False
            self.torque_on = False
            self.motion = None

    # ------------------------------------------------------------ 动作
    def press(self, key: str) -> None:
        """方向按下：扭矩关（E 后）则先重新 prepare。"""
        with self._lock:
            motion = cc.KEY_MOTIONS.get(key.lower())
            if motion is None or motion is cc.Motion.STOP:
                return
            if not self.connected:
                return
            if not self.torque_on:
                try:
                    cc.prepare(self.ser, self.config, print_status=False)
                    self.torque_on = True
                except Exception:
                    return
            self.motion = motion

    def release(self) -> None:
        with self._lock:
            self.motion = None

    def estop(self) -> None:
        """0 速 + 扭矩关（同 camera_car_drive 的 E）。"""
        with self._lock:
            self.motion = None
            if self.connected and self.ser is not None:
                try:
                    cc.stop(self.ser, self.config)
                    cc.close_torque(self.ser, self.config)
                except Exception:
                    pass
                self.torque_on = False

    # ------------------------------------------------------------ 循环
    def _start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _stop_loop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._last_tick >= SEND_PERIOD:
                self._last_tick = now
                try:
                    with self._lock:
                        if not self.connected or self.ser is None:
                            continue
                        if self.motion is None:
                            cc.stop(self.ser, self.config)      # 0 速刹停（保持扭矩）
                        else:
                            cc.command(self.ser, self.config, self.motion)
                except Exception as exc:
                    self._error = str(exc)
                    self._stop.set()
            time.sleep(0.004)
        # 循环退出兜底：0 速
        with self._lock:
            if self.connected and self.ser is not None:
                try:
                    cc.stop(self.ser, self.config)
                except Exception:
                    pass

    # ------------------------------------------------------------ 状态
    def state(self) -> dict:
        with self._lock:
            return {
                "connected": self.connected,
                "port": self.port,
                "motion": None if self.motion is None else self.motion.value,
                "torque_on": self.torque_on,
                "error": self._error,
            }
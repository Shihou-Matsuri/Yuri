"""主动臂 -> 从动臂遥操作桥（PC 侧）。

主动臂（SO101Leader）接电脑 USB，人握着操作；本模块循环读取其 6 个关节角，
映射到归一化目标后经 :mod:`esp32_transport` 发给 ESP32-S3 无线执行端，
由 ESP32 通过 UART1 驱动从动臂（SO101Follower / 6×STS3215）。

安全：死区抑制抖动、限速、限位截断、主动臂断连/异常 -> 立即 estop。
从动臂与小车互斥：本模块运行期间不应有 car_drive；调用方需保证（见任务文档）。

接口设计（可测试）：LeaderBridge 不直接持有硬件，而是接受三个可替换部件：
    - leader: 实现 .get_action() -> dict[str,float]（".pos" 后缀）
    - transport: 实现 send() / recv() / close()（见 esp32_transport）
    - 这些用 Fake/Mock 即可离线验证映射/安全/急停逻辑（tests/test_leader_bridge.py）。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

from .config import JOINT_NAMES

logger = logging.getLogger(__name__)


class LeaderLike(Protocol):
    """主动臂读取接口（只依赖 lerobot SO101Leader.get_action 的形态）。"""

    def get_action(self) -> dict[str, float]: ...
    def disconnect(self) -> None: ...


class TransportLike(Protocol):
    def send(self, obj: dict[str, Any]) -> None: ...
    def recv(self, timeout_s: float) -> dict[str, Any] | None: ...
    def close(self) -> None: ...


# 身体关节归一化范围（-100..100）；gripper 单独 0..100（与 lerobot use_degrees=False 一致）
BODY_JOINTS = [j for j in JOINT_NAMES if j != "gripper"]
GRIPPER = "gripper"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class LeaderBridge:
    """主动臂遥操作桥主逻辑。

    参数全部由外部传入（config 驱动），本类不读文件、不硬编码关节表。
    """

    def __init__(
        self,
        *,
        joint_limits: dict[str, tuple[float, float]],
        max_velocity: float,
        deadband: float = 0.5,
        read_hz: float = 30.0,
        send_hz: float = 20.0,
        estop_tolerance_s: float = 1.0,
    ):
        """
        joint_limits: 各关节允许范围 (min,max)，归一化单位。
        max_velocity: 相邻发送帧关节变化量上限（归一化单位/帧）。
        deadband:     死区——关节位置变化小于此值不触发新发送（抑制抖动）。
        read_hz:      主动臂读取频率。
        send_hz:      ESP32 发送频率（≥2Hz 喂看门狗）。
        estop_tolerance_s: 主动臂多久没读到有效值即判定断连 -> 急停。
        """
        # 校验关节表完整
        missing = set(JOINT_NAMES) - set(joint_limits)
        if missing:
            raise ValueError(f"joint_limits 缺少关节: {sorted(missing)}")
        self._joint_limits = joint_limits
        self._max_velocity = max_velocity
        self._deadband = deadband
        self._read_hz = read_hz
        self._send_hz = send_hz
        self._estop_tolerance_s = estop_tolerance_s

        self._last_target: dict[str, float] | None = None
        self._estop = False
        self._last_read_ok = 0.0

    # ------------------------------------------------------------------ 安全
    @property
    def estop_active(self) -> bool:
        return self._estop

    def estop(self) -> None:
        """触发急停（置标志 + 尝试给 ESP32 发 estop）。由调用方在 finally 里 ensure。"""
        self._estop = True

    # ------------------------------------------------------------------ 映射
    def _map_and_clip(self, action: dict[str, float]) -> dict[str, float]:
        """原始 .pos 关节值 -> 归一化目标（去 .pos、clamp 到 joint_limits）。"""
        targets: dict[str, float] = {}
        for name, val in action.items():
            motor = name[:-4] if name.endswith(".pos") else name
            if motor not in JOINT_NAMES:
                continue  # 忽略未知键（兼容不同 lerobot 返回）
            lo, hi = self._joint_limits[motor]
            targets[motor] = _clamp(float(val), lo, hi)
        return targets

    def _apply_deadband(self, new: dict[str, float]) -> dict[str, float]:
        """只保留相对上次发送变化超过死区的关节（首次全发）。"""
        if self._last_target is None:
            return dict(new)
        changed = {
            m: v
            for m, v in new.items()
            if m in self._last_target and abs(v - self._last_target[m]) >= self._deadband
        }
        # 保持所有关节都在目标集（避免只发变化关节导致其他关节停发）
        out = dict(self._last_target)
        out.update(changed)
        return out

    def _limit_velocity(self, new: dict[str, float]) -> dict[str, float]:
        """限制相邻帧最大变化量（防跳变/速度过冲）。"""
        if self._last_target is None:
            return dict(new)
        out = dict(new)
        for m, v in new.items():
            prev = self._last_target.get(m, v)
            delta = v - prev
            if abs(delta) > self._max_velocity:
                out[m] = prev + (self._max_velocity if delta > 0 else -self._max_velocity)
        return out

    # ------------------------------------------------------------------ 主循环
    def step(
        self,
        leader: LeaderLike,
        transport: TransportLike,
    ) -> dict[str, float] | None:
        """单步：读主动臂 -> 映射/安全 -> 需要时发送。返回本轮发送的目标或 None。"""
        if self._estop:
            return None

        # 1. 读主动臂
        try:
            raw_action = leader.get_action()
        except Exception as exc:  # noqa: BLE001 —— 读取失败视为断连
            logger.warning("读取主动臂失败: %s -> 急停", exc)
            self._estop = True
            self._send_estop(transport)
            return None

        if not raw_action:
            # 空 dict 也视为异常（无有效关节读数）
            logger.warning("主动臂返回空读数 -> 急停")
            self._estop = True
            self._send_estop(transport)
            return None

        self._last_read_ok = time.monotonic()

        # 2. 归一化 + 限位
        mapped = self._map_and_clip(raw_action)

        # 3. 限速
        mapped = self._limit_velocity(mapped)

        # 4. 死区（决定是否值得发）
        to_send = self._apply_deadband(mapped)
        self._last_target = mapped  # 用最新映射更新，不发也记录位置

        # 5. 发送（即使目标没变，心跳靠调用方按 send_hz 持续调 step）
        self._send_move_joints(transport, to_send)
        return to_send

    # ------------------------------------------------------------------ 发送
    def _send_move_joints(self, transport: TransportLike, targets: dict[str, float]) -> None:
        cmd = {
            "cmd": "move_joints",
            "params": {"targets": targets, "duration": 1.0 / self._send_hz},
        }
        try:
            transport.send(cmd)
        except Exception as exc:  # noqa: BLE001
            logger.error("发送 move_joints 失败: %s -> 急停", exc)
            self._estop = True

    def _send_estop(self, transport: TransportLike) -> None:
        try:
            transport.send({"cmd": "estop", "params": {}})
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 运行
    def run(
        self,
        leader: LeaderLike,
        transport: TransportLike,
        *,
        stop_event: Any = None,
    ) -> None:
        """持续运行：read_hz 读、send_hz 发。stop_event 提供 is_set() 则用于优雅停止。"""
        logger.info("遥操作桥启动: 读 %.0fHz / 发 %.0fHz", self._read_hz, self._send_hz)
        read_period = 1.0 / self._read_hz
        send_period = 1.0 / self._send_hz
        next_send = 0.0
        while not self._estop:
            if stop_event is not None and stop_event.is_set():
                break
            t0 = time.monotonic()

            # 读频率内持续读并 step（step 内部按 deadband 决定是否真发）
            if time.monotonic() >= next_send:
                self.step(leader, transport)
                next_send = time.monotonic() + send_period

            # 主动臂断连检测：超时未读到有效值 -> 急停
            if self._last_read_ok and (time.monotonic() - self._last_read_ok) > self._estop_tolerance_s:
                logger.warning("主动臂 %.1fs 未读数 -> 急停", self._estop_tolerance_s)
                self._estop = True
                self._send_estop(transport)
                break

            # 限速
            elapsed = time.monotonic() - t0
            sleep = read_period - elapsed
            if sleep > 0:
                time.sleep(sleep)

        # 收尾：确保急停已发
        self._send_estop(transport)
        logger.info("遥操作桥结束（estop=%s）", self._estop)

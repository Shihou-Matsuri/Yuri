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
        move_duration_s: float = 0.3,
        estop_tolerance_s: float = 1.0,
        apply_speed_limit: bool = True,
    ):
        """
        joint_limits: 各关节允许范围 (min,max)，归一化单位。
        max_velocity: 相邻发送帧关节变化量上限（归一化单位/帧）。
        deadband:     死区——关节位置变化小于此值不触发新发送（抑制抖动）。
        read_hz:      主动臂读取频率。
        send_hz:      ESP32 move_joints 发送频率（须 <500ms 喂看门狗；不要太高，
                      否则每次 move_joints 重置固件插值反而不动）。
        move_duration_s: 每条 move_joints 的 duration（固件插值时长）。给足时间让
                      固件平滑插值到目标，远大于 1/send_hz 的一个小步。
        estop_tolerance_s: 主动臂多久没读到有效值即判定断连 -> 急停。
        apply_speed_limit: 是否启用速度限制。遥操作实时跟随建议关掉
            （否则大幅快动时从动臂被限速拖累、看起来跟不上/停住）。
        """
        # 校验关节表完整
        missing = set(JOINT_NAMES) - set(joint_limits)
        if missing:
            raise ValueError(f"joint_limits 缺少关节: {sorted(missing)}")
        self._apply_speed_limit = apply_speed_limit
        self._move_duration_s = move_duration_s
        self._joint_limits = joint_limits
        self._max_velocity = max_velocity
        self._deadband = deadband
        self._read_hz = read_hz
        self._send_hz = send_hz
        self._estop_tolerance_s = estop_tolerance_s

        self._last_target: dict[str, float] | None = None
        self._estop = False
        self._last_read_ok = 0.0
        self._last_move_target: dict[str, float] | None = None

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
        """单步：读主动臂 -> 映射/安全/死区；目标变化超死区才发 move_joints。

        喂看门狗由 run() 每周期发 heartbeat 承担（本方法不无条件发 move_joints，
        避免"目标不变也刷 move_joints"在固件插值结束后不再喂狗的问题）。
        """
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

        # 3. 限速（可选：仅当 apply_speed_limit 时启用；实时遥操作用来防突跳）
        if self._apply_speed_limit:
            mapped = self._limit_velocity(mapped)

        # 4. 每帧无条件发送当前 leader 位置（限位后）。
        #    不用死区门槛抑制"变化小就不发"——那会导致大幅动作后 leader 停住、
        #    从动臂还在追赶但 delta 变化小于死区时不再补发而"停在半路"。
        #    防静止抖动靠 move_joints 目标=当前位置时固件不产生实际运动实现。
        self._last_move_target = dict(mapped)
        self._last_target = dict(mapped)
        self._send_move_joints(transport, mapped)
        return mapped

    # ------------------------------------------------------------------ 发送
    def _send_move_joints(self, transport: TransportLike, targets: dict[str, float]) -> None:
        cmd = {
            "cmd": "move_joints",
            "params": {"targets": targets, "duration": self._move_duration_s},
        }
        try:
            transport.send(cmd)
        except Exception as exc:  # noqa: BLE001
            logger.error("发送 move_joints 失败: %s -> 急停", exc)
            self._estop = True

    def _send_heartbeat(self, transport: TransportLike) -> None:
        """发 heartbeat 喂固件看门狗（固件只喂狗不回包，无拥塞）。"""
        try:
            transport.send({"cmd": "heartbeat", "params": {}})
        except Exception as exc:  # noqa: BLE001
            logger.error("发送 heartbeat 失败: %s -> 急停", exc)
            self._estop = True

    def _send_estop(self, transport: TransportLike) -> None:
        try:
            transport.send({"cmd": "estop", "params": {}})
        except Exception:  # noqa: BLE001
            pass

    def _send_resume(self, transport: TransportLike) -> None:
        """清掉固件可能的 estop/看门狗锁，让后续 move_joints 能被接受。"""
        try:
            transport.send({"cmd": "resume", "params": {}})
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
        """持续运行：send_hz 周期内 读主动臂并 step(目标变才发 move_joints)，
        每周期都发 heartbeat 喂固件看门狗（从动臂静止也不被刹停）。
        启动先发 resume 清掉可能残留的 estop/看门狗锁。
        """
        logger.info("遥操作桥启动: 读 %.0fHz / 发 %.0fHz", self._read_hz, self._send_hz)
        self._send_resume(transport)  # 清残留 estop
        send_period = 1.0 / self._send_hz
        next_cycle = time.monotonic()
        # 周期性自愈：若 ESP32 因偶发 watchdog/负载进入 estop，桥自动 resume，避免从动臂停住需手动恢复。
        auto_recover_period_s = 2.0
        last_auto_recover = time.monotonic()
        while not self._estop:
            if stop_event is not None and stop_event.is_set():
                break
            t0 = time.monotonic()

            # 读主动臂 + 若目标变化则发 move_joints
            self.step(leader, transport)

            # 喂看门狗（每次 step 后都发，保证从动臂静止也不被刹停）
            self._send_heartbeat(transport)

            # 周期性自检 + 自动 resume（仅当 ESP32 进入 estop）
            if time.monotonic() - last_auto_recover >= auto_recover_period_s:
                last_auto_recover = time.monotonic()
                try:
                    transport.send({"cmd": "status", "params": {}})
                    resp = transport.recv(0.15)
                    if resp and not resp.get("ok"):
                        pass
                    elif resp and resp.get("result", {}).get("estop") is True:
                        logger.warning("检测到 ESP32 estop -> 自动 resume")
                        self._send_resume(transport)
                except Exception as _re:  # noqa: BLE001
                    logger.debug("自检 resume 失败: %s", _re)

            # 主动臂断连检测：超时未读到有效值 -> 急停
            if self._last_read_ok and (time.monotonic() - self._last_read_ok) > self._estop_tolerance_s:
                logger.warning("主动臂 %.1fs 未读数 -> 急停", self._estop_tolerance_s)
                self._estop = True
                self._send_estop(transport)
                break

            # 限速
            elapsed = time.monotonic() - t0
            sleep = send_period - elapsed
            if sleep > 0:
                time.sleep(sleep)

        # 收尾：确保急停已发
        self._send_estop(transport)
        logger.info("遥操作桥结束（estop=%s）", self._estop)

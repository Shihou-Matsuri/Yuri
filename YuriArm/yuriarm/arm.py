"""机械臂控制后端抽象与实现。

分层设计：
- :class:`ArmBackend`：最小硬件原语（读位置 / 写目标 / 读寄存器 / 力矩开关 / 遥测）
- :class:`MockArm`：纯 Python 仿真后端（离线测试、--mock、CI 冒烟，无硬件依赖）
- :class:`LerobotArm`：包装父仓库 lerobot 的 SO101Follower（真机，COM 口）。
  lerobot 只在 connect() 内惰性导入，保证本模块在任意 Python 中可导入。
- :class:`YuriArm`：门面——安全（限速/限位/忙锁/急停）+ 高层原语
  （移动 / 姿态 / 夹爪负载判定 / 示教-回放拾取 / 遥测）。

兼容性说明（硬约束 #1）：本模块不修改 lerobot 任何源码；真机路径只使用
SO101Follower 的公共接口（bus.sync_read / sync_write / read / enable_torque /
disable_torque / disconnect），与 lerobot_teleoperate、数据采集等其他功能
在"同一运行时上下文"中可安全共存——它们各自持有独立的 FeetechMotorsBus 实例，
唯一的外部共享资源是 COM 口：同一时刻只能有一个进程占用（文档已注明）。
"""
from __future__ import annotations

import abc
import threading
import time
from typing import Any, Callable

from .config import JOINT_NAMES, ArmConfig


class ArmError(RuntimeError):
    """机械臂控制通用错误。"""


class ArmNotConnectedError(ArmError):
    pass


class ArmEStopError(ArmError):
    """急停被触发（外部 estop 或负载超限）。"""


class CalibrationMissingError(ArmError):
    pass


class ArmState:
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    BUSY = "busy"
    ESTOPPED = "estop"

    @classmethod
    def all(cls) -> tuple[str, ...]:
        return (cls.DISCONNECTED, cls.CONNECTED, cls.BUSY, cls.ESTOPPED)


class ArmBackend(abc.ABC):
    """硬件后端抽象：YuriArm 通过它驱动任意实现（真机/仿真/未来 ESP32）。"""

    name: str = "abstract"

    @abc.abstractmethod
    def connect(self) -> None: ...

    @abc.abstractmethod
    def disconnect(self) -> None: ...

    @abc.abstractmethod
    def is_connected(self) -> bool: ...

    @abc.abstractmethod
    def read_positions(self) -> dict[str, float]:
        """读取所有关节当前位置（归一化单位）。"""

    @abc.abstractmethod
    def write_goal(self, targets: dict[str, float]) -> None:
        """一次性写入目标关节角（归一化单位）；不含插值。"""

    @abc.abstractmethod
    def read_register(self, name: str, motor: str) -> float:
        """读取电机寄存器原始值（如 Present_Load / Present_Voltage / Present_Temperature）。"""

    def read_loads(self) -> dict[str, float]:
        """读取全部关节负载（归一化/解码后的带符号负载）。默认逐关节读，可覆盖为 sync_read。"""
        return {m: self.read_register("Present_Load", m) for m in JOINT_NAMES}

    @abc.abstractmethod
    def set_torque(self, on: bool) -> None: ...

    @abc.abstractmethod
    def telemetry(self) -> dict[str, Any]:
        """返回遥测 dict：{positions, loads, voltage, temperature, ...}。"""


class MockArm(ArmBackend):
    """纯 Python 仿真后端。

    - write_goal 立即生效（模拟总线写后位置即到位，便于确定性测试插值/急停逻辑）；
    - set_block(True) 后在 gripper 合拢方向产生负载跳变并钳位位置（模拟夹到方块）；
    - 遥测返回固定电压/温度与实时负载。
    """

    name = "mock"

    def __init__(self, initial: dict[str, float] | None = None):
        self._positions: dict[str, float] = dict(initial or {m: 0.0 for m in JOINT_NAMES})
        self._torque_on = False
        self._connected = False
        self._blocked = False
        self._load: dict[str, float] = {m: 0.0 for m in JOINT_NAMES}
        self._gripper_stuck_at: float | None = None

    # -- 测试辅助 --
    def set_block(self, blocked: bool) -> None:
        """模拟/解除夹爪间有方块。"""
        self._blocked = blocked
        if not blocked:
            self._gripper_stuck_at = None

    @property
    def block_present(self) -> bool:
        return self._blocked

    # -- ArmBackend --
    def connect(self) -> None:
        self._connected = True
        self._torque_on = True

    def disconnect(self) -> None:
        self._connected = False
        self._torque_on = False

    def is_connected(self) -> bool:
        return self._connected

    def read_positions(self) -> dict[str, float]:
        return dict(self._positions)

    def write_goal(self, targets: dict[str, float]) -> None:
        if not self._connected:
            raise ArmNotConnectedError("mock 后端未连接")
        for motor, val in targets.items():
            if motor not in self._positions:
                raise ArmError(f"未知关节: {motor}")
            if motor == "gripper" and self._blocked:
                cur = self._positions["gripper"]
                # 合拢方向（目标 < 当前）→ 模拟碰到方块：位置钳位、负载跳变
                if val < cur:
                    self._gripper_stuck_at = cur
                    self._load["gripper"] = 1000.0
                    continue
                self._gripper_stuck_at = None
                self._load["gripper"] = 0.0
            self._positions[motor] = float(val)

    def read_register(self, name: str, motor: str) -> float:
        if name == "Present_Load":
            return self._load.get(motor, 0.0)
        if name == "Present_Voltage":
            return 7.4
        if name == "Present_Temperature":
            return 35.0
        raise ArmError(f"mock 后端不支持寄存器 '{name}'")

    def set_torque(self, on: bool) -> None:
        self._torque_on = on

    def telemetry(self) -> dict[str, Any]:
        return {
            "positions": dict(self._positions),
            "loads": dict(self._load),
            "voltage": 7.4,
            "temperature": 35.0,
            "torque_on": self._torque_on,
        }


class LerobotArm(ArmBackend):
    """真机后端：包装 lerobot SO101Follower。

    注意：lerobot 只在 connect() 中导入，避免本包在无 lerobot 环境下导入失败。
    标定文件位于 ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/{id}.json，
    缺失或与电机不一致时必须先运行交互式标定（`yuriarm calibrate`）。
    """

    name = "lerobot"

    def __init__(self, config: ArmConfig):
        self._config = config
        self._robot = None  # SO101Follower 实例（惰性创建）

    def _require_robot(self):
        if self._robot is None:
            raise ArmNotConnectedError("未连接机械臂（先调用 connect()）")
        return self._robot

    def connect(self) -> None:
        # 惰性导入 lerobot（兼容性：只有真机路径才依赖父仓库）
        try:
            from lerobot.robots.so101_follower import SO101Follower
            from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
        except ImportError as e:
            raise ArmError(
                "无法导入 lerobot（请使用 lerobot conda 环境运行真机模式）"
            ) from e

        arm_cfg = self._config.arm
        robot_cfg = SO101FollowerConfig(
            port=arm_cfg["port"],
            id=arm_cfg["id"],
            # 是否在断开时关闭力矩：默认 True（安全），但连续指令演示/服务器模式
            # 需要保持力矩（False），否则每跑完一条命令臂就失力下垂
            disable_torque_on_disconnect=bool(arm_cfg.get("disable_torque_on_disconnect", True)),
        )
        robot = SO101Follower(robot_cfg)

        if not robot.calibration_fpath.is_file():
            raise CalibrationMissingError(
                f"未找到标定文件: {robot.calibration_fpath}\n"
                "请先运行交互式标定: python -m yuriarm calibrate --config <path>"
            )

        robot.connect(calibrate=False)
        if not robot.is_calibrated:
            raise ArmError(
                "电机内标定与标定文件不一致，拒绝继续（防止越界）。\n"
                "请运行: python -m yuriarm calibrate --config <path>"
            )

        # 连接后应用电机保护参数覆盖（如 5V 下夹爪过载阈值，见 config.py 说明）
        for motor, regs in (arm_cfg.get("motor_overrides") or {}).items():
            if motor not in robot.bus.motors:
                continue
            for reg, val in regs.items():
                robot.bus.write(reg, motor, val, normalize=False)

        # 显式开启力矩（lerobot connect 内部会恢复力矩，这里再兜底一次）
        robot.bus.enable_torque()
        self._robot = robot

    def disconnect(self) -> None:
        robot = self._require_robot()
        robot.disconnect()
        self._robot = None

    def is_connected(self) -> bool:
        return self._robot is not None and self._robot.bus.is_connected

    def read_positions(self) -> dict[str, float]:
        return dict(self._require_robot().bus.sync_read("Present_Position"))

    def write_goal(self, targets: dict[str, float]) -> None:
        self._require_robot().bus.sync_write("Goal_Position", dict(targets))

    def read_register(self, name: str, motor: str) -> float:
        return float(self._require_robot().bus.read(name, motor, normalize=False))

    def read_loads(self) -> dict[str, float]:
        return dict(self._require_robot().bus.sync_read("Present_Load", normalize=False))

    def set_torque(self, on: bool) -> None:
        robot = self._require_robot()
        if on:
            robot.bus.enable_torque()
        else:
            robot.bus.disable_torque()

    def telemetry(self) -> dict[str, Any]:
        robot = self._require_robot()
        positions = self.read_positions()
        loads = dict(robot.bus.sync_read("Present_Load", normalize=False))
        # 电压/温度为每电机原始值，读失败不影响整体遥测
        voltages: list[float] = []
        temperatures: list[float] = []
        for motor in JOINT_NAMES:
            try:
                # Present_Voltage 单位 0.1V（如 55 = 5.5V）
                voltages.append(float(robot.bus.read("Present_Voltage", motor, normalize=False)) / 10.0)
            except Exception:
                pass
            try:
                temperatures.append(float(robot.bus.read("Present_Temperature", motor, normalize=False)))
            except Exception:
                pass
        return {
            "positions": positions,
            "loads": loads,
            "voltage": round(sum(voltages) / len(voltages), 2) if voltages else None,
            "temperature": round(sum(temperatures) / len(temperatures), 1) if temperatures else None,
            "torque_on": True,
        }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class YuriArm:
    """YuriArm 门面：安全 + 高层原语。

    线程模型：运动命令通过 :meth:`_run_exclusive` 串行化（含嵌套，如 pick→move_joints）；
    急停 :meth:`estop` 不获取该锁，可随时打断运动循环。
    """

    def __init__(self, config: ArmConfig, backend: ArmBackend | None = None, *, mock: bool = False):
        self.config = config
        if backend is None:
            backend = MockArm() if mock else LerobotArm(config)
        self._backend = backend
        self._lock = threading.RLock()
        self._busy_depth = 0
        self._estop_flag = False
        self._state = ArmState.DISCONNECTED

    # ------------------------------------------------------------------ 状态
    @property
    def backend(self) -> ArmBackend:
        return self._backend

    @property
    def state(self) -> str:
        return self._state

    def is_connected(self) -> bool:
        # BUSY 表示正在执行运动命令，仍是已连接状态（避免嵌套命令误判为未连接）
        return self._state in (ArmState.CONNECTED, ArmState.BUSY) and self._backend.is_connected()

    def status(self) -> dict[str, Any]:
        poses = {name: dict(joints) for name, joints in self.config.poses.items()}
        return {
            "state": self._state,
            "backend": self._backend.name,
            "connected": self.is_connected(),
            "port": self.config.arm.get("port"),
            "id": self.config.arm.get("id"),
            "poses": poses,
            "target_colors": self.config.blocks.get("target_colors"),
        }

    # ------------------------------------------------------------------ 生命周期
    def connect(self) -> dict[str, Any]:
        with self._lock:
            if self.is_connected():
                return {"state": self._state}
            self._backend.connect()
            self._estop_flag = False
            self._state = ArmState.CONNECTED
            return {"state": self._state, "backend": self._backend.name}

    def disconnect(self) -> dict[str, Any]:
        with self._lock:
            if self._backend.is_connected():
                self._backend.disconnect()
            self._state = ArmState.DISCONNECTED
            return {"state": self._state}

    def calibrate(self) -> dict[str, Any]:
        """交互式标定（真机）。仅控制台可用；mock 后端直接报错。"""
        with self._lock:
            if isinstance(self._backend, MockArm):
                raise ArmError("mock 后端无需标定")
            if not self._backend.is_connected():
                self._backend.connect()
            robot = self._backend._require_robot()  # noqa: SLF001  (同包内访问)
            robot.calibrate()
            return {"calibrated": True, "path": str(robot.calibration_fpath)}

    # ------------------------------------------------------------------ 运动
    def move_joints(
        self,
        targets: dict[str, float],
        *,
        duration: float | None = None,
        max_velocity: float | None = None,
        on_step: Callable[[dict[str, float]], None] | None = None,
    ) -> dict[str, float]:
        """插值移动到目标关节角。

        - 限速：duration 缺省时按最大位移 / max_velocity 计算；
        - 限位：目标超出 joint_limits 直接拒绝（不改写电机寄存器）；
        - 急停：每一步检查 estop 标志，触发则抛 ArmEStopError 并停止发送。
        """
        with self._run_exclusive():
            if not targets:
                raise ArmError("目标关节为空（move_joints 需要至少一个关节目标）")
            unknown = set(targets) - set(JOINT_NAMES)
            if unknown:
                raise ArmError(f"未知关节: {sorted(unknown)}")
            limits = self.config.joint_limits
            for motor, val in targets.items():
                lo, hi = limits[motor]
                if not (lo <= float(val) <= hi):
                    raise ArmError(f"关节 {motor} 目标 {val} 超出限位 [{lo}, {hi}]")
            start = self._backend.read_positions()
            vel = float(max_velocity if max_velocity is not None else self.config.safety["max_velocity"])
            vel = max(vel, 1.0)
            if duration is None:
                deltas = [
                    abs(float(targets.get(m, start.get(m, 0.0))) - start.get(m, 0.0)) for m in start
                ]
                max_delta = max(deltas) if deltas else 0.0
                duration = max_delta / vel
            duration = max(duration, 0.05)
            hz = float(self.config.safety["move_steps_hz"])
            steps = max(1, int(round(duration * hz)))
            step_s = duration / steps
            current = dict(start)
            for i in range(1, steps + 1):
                self._check_estop()
                frac = i / steps
                interp = {
                    m: current[m] + (float(targets.get(m, current[m])) - current[m]) * frac
                    for m in start
                }
                self._backend.write_goal(interp)
                current = interp
                if on_step is not None:
                    on_step(dict(current))
                # 关节负载监控（设计文档 §4.3/§4.4：负载突增=碰撞/堵转 → 立即停）
                # 阈值按关节配置（夹爪默认更高，见 config.py）
                over = self._overload_joints(loads=self._backend.read_loads())
                if over:
                    self.estop()
                    raise ArmEStopError(f"关节负载超限自动急停: {over}")
                if step_s > 0:
                    time.sleep(step_s)
            return dict(self._backend.read_positions())

    def move_to_pose(self, name: str, **kwargs: Any) -> dict[str, float]:
        return self.move_joints(self.config.get_pose(name), **kwargs)

    def record_pose(self, name: str) -> dict[str, float]:
        with self._lock:
            self._require_connected()
            joints = self._backend.read_positions()
            self.config.set_pose(name, joints)
            return joints

    def home(self, **kwargs: Any) -> dict[str, float]:
        return self.move_to_pose("home", **kwargs)

    # ------------------------------------------------------------------ 夹爪
    def open_gripper(self, velocity: float | None = None) -> dict[str, float]:
        return self.move_joints(
            {"gripper": float(self.config.gripper["open"])},
            max_velocity=velocity or float(self.config.gripper["close_velocity"]),
        )

    def close_gripper(
        self,
        *,
        max_load: float | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """合拢夹爪，用 Present_Load 跳变判定"夹住"。

        返回 {"result": "gripped"|"timeout"|"estop", "position", "load"}。
        """
        g = self.config.gripper
        max_load = float(max_load if max_load is not None else g["close_max_load"])
        timeout = float(timeout if timeout is not None else g["close_timeout_s"])
        step = float(g["close_step"])
        interval = float(g["close_interval_s"])

        with self._run_exclusive():
            # 判定必须基于"实际位置"（不能基于本地命令位置——夹到方块时命令位置继续走
            # 但实际被卡住，用命令位置判断会误报 timeout，曾实测）。
            # 夹持确认策略（用户要求）：位置停滞时**用负载确认夹紧**，而不是看到
            # 位置停住就判定——位置停滞可能是"夹住方块"也可能是"电机蠕动/假停滞"：
            #   停滞 → 继续压 → 负载升过 close_confirm_load 才算夹住；
            #   压够 close_confirm_time_s 负载还低 → 判定没夹到真东西（timeout）。
            confirm_load = float(g.get("close_confirm_load", 250.0))
            confirm_time = float(g.get("close_confirm_time_s", 1.5))
            start_pos = self._backend.read_positions()["gripper"]
            target = float(g["close"])
            direction = -1.0 if target < start_pos else 1.0
            deadline = time.monotonic() + timeout
            stall_pos: float | None = None
            stall_since: float | None = None
            while True:
                self._check_estop()
                actual = float(self._backend.read_positions()["gripper"])
                load = float(self._backend.read_register("Present_Load", "gripper"))
                if load > max_load:
                    return {"result": "gripped", "position": actual, "load": load}
                # 实际已合拢到底（空夹爪）→ 没夹到东西
                if (direction < 0 and actual <= target + 0.5) or (direction > 0 and actual >= target - 0.5):
                    return {"result": "timeout", "position": actual, "load": load}
                now = time.monotonic()
                # 位置停滞检测
                if stall_pos is not None and abs(actual - stall_pos) < 0.5:
                    if stall_since is None:
                        stall_since = now
                    # 停滞确认：**直接命令压到底**（小步进目标电机不会憋出大力，实测
                    # 直接压目标负载 500 vs 小步进只有 112），等一拍让力矩建立再读负载：
                    # 负载超过 confirm_load = 夹到真东西；压够 confirm_time 仍低 = 没夹到。
                    self._backend.write_goal({"gripper": target})
                    time.sleep(max(interval, 0.3))
                    actual = float(self._backend.read_positions()["gripper"])
                    load = float(self._backend.read_register("Present_Load", "gripper"))
                    if load > confirm_load:
                        return {"result": "gripped", "position": actual, "load": load}
                    if now - stall_since > confirm_time:
                        return {"result": "timeout", "position": actual, "load": load}
                    continue
                stall_pos = actual
                stall_since = None
                nxt = actual + direction * step
                if direction < 0:
                    nxt = max(nxt, target)
                else:
                    nxt = min(nxt, target)
                self._backend.write_goal({"gripper": nxt})
                if now >= deadline:
                    return {"result": "timeout", "position": actual, "load": load}
                time.sleep(interval)

    # ------------------------------------------------------------------ 拾取
    def pick(
        self,
        *,
        pick_high: str | None = None,
        pick_low: str | None = None,
        drop: str | None = None,
        max_velocity: float | None = None,
    ) -> dict[str, Any]:
        """M0 示教-回放拾取周期（设计文档 §4.4 的有线版）。

        流程：pick_high(高空,夹开) → pick_low(慢速下压) → close_gripper(负载判定)
              → pick_high(垂直提起) → drop(移到料篮) → open_gripper(放下)。

        夹取未成功（timeout）时中止并返回失败，不会带着空爪做提起/投放。
        整个周期持有运动锁，防止其他指令在中间穿插。
        """
        p = self.config.pick
        high = pick_high or p["pick_high_pose"]
        low = pick_low or p["pick_low_pose"]
        drop_pose = drop or p["drop_pose"]
        for name in (high, low, drop_pose):
            if not self.config.poses.get(name):
                raise ArmError(f"姿态 '{name}' 未示教，先运行: python -m yuriarm teach {name}")
            self.config.get_pose(name)  # 提前校验，避免中途才发现缺姿态

        with self._run_exclusive():
            steps: list[dict[str, Any]] = []
            self.move_to_pose(high, max_velocity=max_velocity)
            steps.append({"step": "approach", "pose": high})
            self.move_to_pose(low, max_velocity=max_velocity)
            steps.append({"step": "descend", "pose": low})
            grip = self.close_gripper()
            steps.append({"step": "close", **grip})
            if grip["result"] != "gripped":
                return {"ok": False, "reason": f"夹取失败: {grip['result']}", "steps": steps}
            # 提起/转移必须保持夹爪当前（夹住）位置，不能再按 pick_high/drop 里的张开值动夹爪
            self._move_pose_keep_gripper(high, max_velocity=max_velocity)
            steps.append({"step": "lift", "pose": high})
            self._move_pose_keep_gripper(drop_pose, max_velocity=max_velocity)
            steps.append({"step": "transit", "pose": drop_pose})
            self.open_gripper()
            steps.append({"step": "drop", "result": "opened"})
            return {"ok": True, "steps": steps}

    def _move_pose_keep_gripper(self, name: str, **kwargs: Any) -> dict[str, float]:
        """移动到命名姿态，但保持夹爪当前位置不动（用于夹住后的提起/转移）。"""
        pose = self.config.get_pose(name)
        targets = {m: v for m, v in pose.items() if m != "gripper"}
        if not targets:
            raise ArmError(f"姿态 '{name}' 只有夹爪关节，无法作为转移姿态")
        return self.move_joints(targets, **kwargs)

    # ------------------------------------------------------------------ 急停
    def estop(self) -> dict[str, Any]:
        """急停：置标志 + 关力矩。不获取运动锁，可随时打断运动循环。"""
        self._estop_flag = True
        try:
            if self._backend.is_connected():
                self._backend.set_torque(False)
        except Exception:
            pass
        self._state = ArmState.ESTOPPED
        return {"state": self._state}

    def resume(self) -> dict[str, Any]:
        with self._lock:
            if not self._backend.is_connected():
                raise ArmNotConnectedError("未连接，无法恢复")
            self._estop_flag = False
            self._backend.set_torque(True)
            self._state = ArmState.CONNECTED
            return {"state": self._state}

    def read_telemetry(self) -> dict[str, Any]:
        with self._lock:
            self._require_connected()
            return self._backend.telemetry()

    # ------------------------------------------------------------------ 内部
    def _estop_threshold(self, motor: str) -> float:
        cfg = self.config.safety.get("estop_load", 800.0)
        if isinstance(cfg, dict):
            return float(cfg.get(motor, cfg.get("default", 800.0)))
        return float(cfg)

    def _overload_joints(self, loads: dict[str, float] | None = None) -> dict[str, float]:
        """返回负载绝对值超过该关节阈值的 {关节: 负载}；空 = 无超限。"""
        loads = loads if loads is not None else self._backend.read_loads()
        over: dict[str, float] = {}
        for motor, val in loads.items():
            thr = self._estop_threshold(motor)
            if thr > 0 and abs(val) > thr:
                over[motor] = abs(val)
        return over

    def _check_estop(self) -> None:
        if self._estop_flag:
            raise ArmEStopError("急停已触发")

    def _require_connected(self) -> None:
        if not self.is_connected():
            raise ArmNotConnectedError("机械臂未连接（先运行 connect）")

    def _run_exclusive(self):
        """运动命令串行化上下文（可嵌套）：外层进入置 BUSY，全部退出后恢复。"""

        class _Ctx:
            def __init__(self, owner: YuriArm):
                self.owner = owner

            def __enter__(self):
                lock = self.owner._lock
                lock.acquire()
                try:
                    self.owner._require_connected()
                    if self.owner._busy_depth == 0:
                        self.owner._state = ArmState.BUSY
                    self.owner._busy_depth += 1
                except Exception:
                    lock.release()
                    raise
                return self

            def __exit__(self, exc_type, exc, tb):
                lock = self.owner._lock
                self.owner._busy_depth -= 1
                if self.owner._busy_depth == 0:
                    self.owner._state = (
                        ArmState.ESTOPPED if self.owner._estop_flag else ArmState.CONNECTED
                    )
                lock.release()
                return False

        return _Ctx(self)

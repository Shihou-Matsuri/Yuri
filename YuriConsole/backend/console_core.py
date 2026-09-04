"""综合遥控台核心：连接/指令/状态，复用 YuriChassis/YuriArm 传输层。

- 真机模式：复用 dual_remote 的单循环语义（20Hz：bridge.step + car_drive + heartbeat）。
- mock 模式：无硬件，模拟状态/日志，供前端离线演示（验收 A-E 可离线 mock）。

设计约束（SOUL.md）：
    - 高频指令不回包；500ms 看门狗由 heartbeat 喂；E 只停轮子；关停=0速+estop。
    - 串口/网络单写者：所有发送都在本模块的 writer 线程里做。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_YURICONSOLE = _HERE.parent.parent  # YuriConsole/
_YURICHASSIS = _YURICONSOLE.parent / "YuriChassis"
_YURIARM = _YURICONSOLE.parent / "YuriArm"
for _p in (_YURICHASSIS, _YURIARM):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import kiwi_drive  # noqa: E402
from car_remote import SerialTransport, TcpTransport, build_speeds, encode_command  # noqa: E402
from dual_remote import _JsonTransport  # noqa: E402
import camera_car_gamepad as gamepad_api  # noqa: E402

TICK_HZ = 20.0
SEND_PERIOD = 1.0 / TICK_HZ
ARM_PAD_STEP = 3.0            # 手柄控臂每 tick 关节增量（归一化单位）
ARM_PAN_RANGE = (-100.0, 100.0)
ARM_LIFT_RANGE = (-100.0, -38.0)   # arm.json joint_limits
ARM_ELBOW_RANGE = (-100.0, 100.0)
ARM_PAD_DZ = 0.15

# 方向键名 -> Motion（与 CLI/文档一致）
DIR_KEYS = {
    "w": "forward", "s": "backward", "a": "left", "d": "right",
    "z": "rotate_left", "x": "rotate_right",
}


class ConsoleCore:
    """遥控台状态与指令聚合。线程安全（锁保护状态；发送只在 writer 线程）。"""

    def __init__(self, mock: bool = False) -> None:
        self.mock = mock
        self._lock = threading.RLock()
        self.transport = None
        self.leader = None
        self.bridge = None
        self.connected = False
        self.arm_enabled = True
        self.arm_pad_enabled = False    # 手柄右摇杆控机械臂（速率模式，接管 teleop）
        self.arm_pad_xy = (0.0, 0.0)
        self.arm_pad_cur = None          # (pan, lift) 归一化当前目标
        self._arm_last_targets = {}      # 最近一次 teleop 目标（作手柄起步基准）
        self.car_motion = None          # Motion 或 None（键盘/按钮离散方向）
        self.car_vel = None             # (vx, vy, omega) m/s 连续速度（手柄摇杆）
        self.car_estop = False          # 小车 estop 置位（E 后需恢复）
        self.global_estop = False
        self.link_name = "mock"
        self.leader_port = "COM7"
        self._stop = threading.Event()
        self._thread = None
        self._last_tick = 0.0
        self._last_ping = 0.0
        self._pending_cmds: list[bytes] = []  # 即时指令队列，writer 线程单写者发送
        self._mock_pos = {j: 0.0 for j in ("shoulder_pan", "shoulder_lift", "elbow_flex",
                                            "wrist_flex", "wrist_roll", "gripper")}
        self._mock_v = 0.0
        self.logs = []                  # (ts, level, msg)
        self._log_max = 500
        self.gamepad = None
        self._init_gamepad()

    def _init_gamepad(self) -> None:
        try:
            self.gamepad = gamepad_api.XInputController()
        except Exception:
            self.gamepad = None

    def gamepad_state(self) -> dict:
        if self.gamepad is None:
            return {
                "connected": False,
                "left_x": 0.0,
                "left_y": 0.0,
                "right_x": 0.0,
                "right_y": 0.0,
                "left_trigger": 0.0,
                "right_trigger": 0.0,
                "buttons": {},
                "error": None,
            }
        try:
            snap = self.gamepad.read()
            return {
                "connected": True,
                "left_x": snap.left_x,
                "left_y": snap.left_y,
                "right_x": snap.right_x,
                "right_y": snap.right_y,
                "left_trigger": snap.left_trigger,
                "right_trigger": snap.right_trigger,
                "buttons": {
                    "a": bool(snap.buttons & gamepad_api.BTN_A),
                    "b": bool(snap.buttons & gamepad_api.BTN_B),
                    "x": bool(snap.buttons & gamepad_api.BTN_X),
                    "y": bool(snap.buttons & gamepad_api.BTN_Y),
                    "lb": bool(snap.buttons & gamepad_api.BTN_LB),
                    "rb": bool(snap.buttons & gamepad_api.BTN_RB),
                    "dpad_up": bool(snap.buttons & gamepad_api.BTN_DPAD_UP),
                    "dpad_down": bool(snap.buttons & gamepad_api.BTN_DPAD_DOWN),
                },
                "error": None,
            }
        except gamepad_api.GamepadNotConnectedError:
            return {
                "connected": False,
                "left_x": 0.0,
                "left_y": 0.0,
                "right_x": 0.0,
                "right_y": 0.0,
                "left_trigger": 0.0,
                "right_trigger": 0.0,
                "buttons": {},
                "error": None,
            }
        except Exception as exc:
            return {
                "connected": False,
                "left_x": 0.0,
                "left_y": 0.0,
                "right_x": 0.0,
                "right_y": 0.0,
                "left_trigger": 0.0,
                "right_trigger": 0.0,
                "buttons": {},
                "error": str(exc),
            }

    # ------------------------------------------------------------ 日志
    def log(self, level: str, msg: str) -> None:
        with self._lock:
            self.logs.append((time.strftime("%H:%M:%S"), level, msg))
            if len(self.logs) > self._log_max:
                del self.logs[: len(self.logs) - self._log_max]

    def get_logs(self, level: str | None = None) -> list[dict]:
        with self._lock:
            out = [{"t": t, "level": lv, "msg": m} for t, lv, m in self.logs]
        if level:
            out = [x for x in out if x["level"] == level]
        return out

    # ------------------------------------------------------------ 连接
    def connect(self, *, link: str = "tcp", serial_port: str | None = None,
                leader_port: str = "COM7") -> str:
        with self._lock:
            if self.connected:
                return "already connected"
            if self.mock:
                self.connected = True
                self.link_name = "mock"
                self.log("info", "mock 模式已连接（离线演示）")
                self._start_writer()
                return "ok"
            try:
                if link == "serial":
                    raw = SerialTransport(serial_port)
                    self.link_name = f"USB {serial_port}"
                else:
                    raw = TcpTransport("192.168.4.1", 8765)
                    self.link_name = "TCP 192.168.4.1:8765"
                transport = _JsonTransport(raw)
                from tools.leader_remote import _make_leader  # noqa: PLC0415
                from dual_remote import _load_bridge  # noqa: PLC0415
                leader = _make_leader(leader_port, mock=False)
                leader.connect(calibrate=False)
                bridge = _load_bridge()
            except Exception as exc:
                self.log("error", f"连接失败: {exc}")
                return f"error: {exc}"
            self.transport = transport
            self.leader = leader
            self.bridge = bridge
            self.leader_port = leader_port
            self.connected = True
            self.global_estop = False
            self.car_estop = False
            self.transport.send(b'{"cmd":"resume"}\n')
            self.transport.send(b'{"cmd":"car_resume"}\n')
            self.log("info", f"已连接 {self.link_name}（leader {leader_port}）")
            self._start_writer()
            return "ok"

    def disconnect(self) -> None:
        with self._lock:
            self._stop_writer()
            if self.mock:
                self.connected = False
                self.log("info", "mock 已断开")
                return
            if self.connected and self.transport is not None:
                try:
                    self.transport.send(b'{"cmd":"car_drive","params":{"raw":[0,0,0]}}\n')
                    self.transport.send(b'{"cmd":"estop"}\n')
                    time.sleep(0.2)
                except Exception:
                    pass
                try:
                    if self.leader is not None:
                        self.leader.disconnect()
                except Exception:
                    pass
                try:
                    self.transport.close()
                except Exception:
                    pass
            self.connected = False
            self.transport = None
            self.leader = None
            self.bridge = None
            self.log("info", "已断开")

    def _start_writer(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._thread.start()

    def _stop_writer(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    # ------------------------------------------------------ 主循环(writer)
    def _writer_loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._last_tick >= SEND_PERIOD:
                self._last_tick = now
                try:
                    self._tick()
                except Exception as exc:
                    self.log("error", f"链路异常: {exc}")
                    with self._lock:
                        self.connected = False
                        self.car_motion = None
                    try:
                        if self.leader is not None:
                            self.leader.disconnect()
                    except Exception:
                        pass
                    try:
                        if self.transport is not None:
                            self.transport.close()
                    except Exception:
                        pass
                    with self._lock:
                        self.leader = None
                        self.bridge = None
                        self.transport = None
                    self._stop.set()
            time.sleep(0.004)

    def _tick(self) -> None:
        if self.mock:
            self._mock_tick()
            return
        if self.transport is None or not self.connected:
            return
        now = time.monotonic()
        # 0. 先发即时指令（急停/恢复等入队项；单写者：仅本 writer 线程 send）
        self._flush_pending()
        # 1. 机械臂：手柄控臂接管，否则 leader 遥操作（teleop_joints 直写）
        if self.arm_pad_enabled:
            self._arm_pad_tick()
        elif self.arm_enabled and self.bridge is not None and self.leader is not None:
            self.bridge.step(self.leader, self.transport)
            try:
                self._arm_last_targets = dict(self.bridge._last_target or {})
            except Exception:
                pass
        # 2. 小车：手柄连续速度 > 离散方向 > 0 速刹停
        if self.car_vel is not None:
            speeds = build_speeds(*self.car_vel)
        elif self.car_motion is None:
            speeds = [0, 0, 0]
        else:
            speeds = build_speeds(*kiwi_drive.MOTION_VECTORS[self.car_motion])
        self.transport.send(encode_command(speeds))
        # 3. heartbeat 喂看门狗
        self.transport.send(b'{"cmd":"heartbeat"}\n')
        # TCP 静默断开检测（自动重连 + resume）
        if "TCP" in self.link_name and now - self._last_ping >= 1.0:
            self._last_ping = now
            if not self.transport.ping_ok():
                self.log("warn", "连接断开 -> 自动重连")
                self.transport.reconnect()
                self.transport.send(b'{"cmd":"resume"}\n')
                self.transport.send(b'{"cmd":"car_resume"}\n')

    # ------------------------------------------------------------ 动作
    def car_press(self, key: str) -> None:
        """方向按下：E 急停后先恢复小车再设目标。"""
        with self._lock:
            motion = kiwi_drive.KEY_MOTIONS.get(key.lower())
            if motion is None:
                return
            if self.car_estop:
                self._enqueue_cmd(b'{"cmd":"car_resume"}\n')
                self.car_estop = False
                self.log("info", "小车已恢复（car_resume）")
            self.car_motion = motion
            self.car_vel = None

    def car_release(self) -> None:
        with self._lock:
            self.car_motion = None
            self.car_vel = None

    def car_vel_set(self, vx: float, vy: float, omega: float) -> None:
        """手柄摇杆连续速度（m/s、rad/s）。与离散方向互斥。"""
        with self._lock:
            if self.car_estop:
                self._enqueue_cmd(b'{"cmd":"car_resume"}\n')
                self.car_estop = False
            self.car_vel = (vx, vy, omega)
            self.car_motion = None

    def car_estop_cmd(self) -> None:
        """轮子急停（car_stop），不碰机械臂。"""
        with self._lock:
            self.car_motion = None
            self.car_vel = None
            self.car_estop = True
            self._enqueue_cmd(b'{"cmd":"car_stop"}\n')
            self.log("warn", "轮子急停（car_stop）")

    def global_estop_cmd(self) -> None:
        """全局急停（臂+车）。"""
        with self._lock:
            self.car_motion = None
            self.global_estop = True
            self.car_estop = True
            self._enqueue_cmd(b'{"cmd":"estop"}\n')
            self.log("error", "全局急停（estop）")

    def resume_cmd(self) -> None:
        with self._lock:
            self.global_estop = False
            self.car_estop = False
            self._enqueue_cmd(b'{"cmd":"resume"}\n')
            self._enqueue_cmd(b'{"cmd":"car_resume"}\n')
            self.log("info", "已恢复（resume + car_resume）")

    def _clamp_arm(self, pan: float, lift: float, elbow: float = 0.0):
        lo_p, hi_p = ARM_PAN_RANGE
        lo_l, hi_l = ARM_LIFT_RANGE
        lo_e, hi_e = ARM_ELBOW_RANGE
        return (max(lo_p, min(hi_p, pan)),
                max(lo_l, min(hi_l, lift)),
                max(lo_e, min(hi_e, elbow)))

    def arm_pad_set(self, enabled: bool, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        """手柄控机械臂（速率积分）：
        x = 右摇杆左右 -> shoulder_pan；y = 右摇杆上下 -> shoulder_lift；
        z = 十字键上下 -> elbow_flex（前后）。"""
        with self._lock:
            was = self.arm_pad_enabled
            self.arm_pad_enabled = bool(enabled)
            self.arm_pad_xy = (float(x), float(y), float(z))
            if enabled and not was:
                # 以最近遥操作目标为起点，避免切换瞬间跳变
                pan = float(self._arm_last_targets.get("shoulder_pan", 0.0))
                lift = float(self._arm_last_targets.get("shoulder_lift", -69.0))
                elbow = float(self._arm_last_targets.get("elbow_flex", 0.0))
                self.arm_pad_cur = self._clamp_arm(pan, lift, elbow)
            if not enabled:
                self.arm_pad_cur = None

    def _arm_pad_tick(self) -> None:
        """20Hz 速率积分：输入越死区则朝该方向持续移动，回中保持。"""
        if self.transport is None or not self.connected:
            return
        x, y, z = self.arm_pad_xy
        cur = self.arm_pad_cur
        if cur is None:
            cur = self._clamp_arm(
                float(self._arm_last_targets.get("shoulder_pan", 0.0)),
                float(self._arm_last_targets.get("shoulder_lift", -69.0)),
                float(self._arm_last_targets.get("elbow_flex", 0.0)))
            self.arm_pad_cur = cur
        pan, lift, elbow = cur
        if abs(x) > ARM_PAD_DZ or abs(y) > ARM_PAD_DZ or abs(z) > ARM_PAD_DZ:
            pan += x * ARM_PAD_STEP          # 右推 -> pan 增大（方向待真机确认）
            lift -= y * ARM_PAD_STEP         # 上推(y<0) -> lift 增大（抬）
            elbow += z * ARM_PAD_STEP        # 十字键上(z>0) -> elbow 增大（方向待真机确认）
            pan, lift, elbow = self._clamp_arm(pan, lift, elbow)
            self.arm_pad_cur = (pan, lift, elbow)
            self.transport.send({
                "cmd": "teleop_joints",
                "params": {"targets": {
                    "shoulder_pan": round(pan, 2),
                    "shoulder_lift": round(lift, 2),
                    "elbow_flex": round(elbow, 2),
                }},
            })

    def gripper_cmd(self, action: str) -> None:
        """夹爪：open / close（close 走固件负载判定）。"""
        if action not in ("open", "close"):
            return
        cmd = "open_gripper" if action == "open" else "close_gripper"
        self._enqueue_cmd((json.dumps({"cmd": cmd, "params": {}}) + "\n").encode("utf-8"))
        self.log("info", f"夹爪 {action}")

    def set_arm_enabled(self, on: bool) -> None:
        with self._lock:
            self.arm_enabled = bool(on)

    def _enqueue_cmd(self, data: bytes) -> None:
        """即时指令入队，由 writer 线程统一发送（保持串口/网络单写者）。"""
        if self.mock:
            return
        with self._lock:
            self._pending_cmds.append(data)

    def _flush_pending(self) -> None:
        with self._lock:
            pending, self._pending_cmds = self._pending_cmds, []
        for data in pending:
            try:
                self.transport.send(data)
            except Exception as exc:
                self.log("error", f"发送失败: {exc}")

    # ------------------------------------------------------------ mock
    def _mock_tick(self) -> None:
        t = time.time()
        for i, j in enumerate(self._mock_pos):
            self._mock_pos[j] = round(18.0 * (0.5 + 0.5 * __import__("math").sin(t * 0.6 + i)), 1)
        self._mock_v = 0.0 if (self.car_motion is None and self.car_vel is None) else 120.0

    def state(self) -> dict:
        """前端轮询的聚合状态。"""
        with self._lock:
            motion = None if self.car_motion is None else self.car_motion.value
            return {
                "connected": self.connected,
                "link": self.link_name,
                "mock": self.mock,
                "leader_port": self.leader_port,
                "arm_enabled": self.arm_enabled,
                "arm_pad_enabled": self.arm_pad_enabled,
                "car_motion": motion,
                "car_vel": self.car_vel,
                "car_estop": self.car_estop,
                "global_estop": self.global_estop,
                "positions": dict(self._mock_pos) if self.mock else {},
                "wheel_speed": self._mock_v if self.mock else None,
            }

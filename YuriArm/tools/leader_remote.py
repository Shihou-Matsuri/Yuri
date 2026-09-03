"""主动臂遥控从动臂：命令行入口。

读主动臂关节角 -> 映射/安全 -> 经 ESP32 无线执行端驱动从动臂。

用法:
    python tools/leader_remote.py                       # 默认: 读 leader.json, TCP 到 ESP32
    python tools/leader_remote.py --config ../configs/leader.json --link tcp
    python tools/leader_remote.py --mock                # 无硬件: 仿真主动臂 (演示循环)
    python tools/leader_remote.py --link serial --serial COM18   # USB 连 ESP32
    python tools/leader_remote.py --check               # 只检测并退出(不进入遥控)

停止: Ctrl+C 会发 estop 并退出。

真机前置:
    1. 主动臂 USB 插电脑 (默认 COM7, 见 --leader-port)
    2. ESP32-S3 已上电并连上 (WiFi AP 192.168.4.1:8765, 或 USB COM18)
    3. 从动臂 6×STS3215 接 ESP32 UART1, 已供电
    4. 小车 (car_drive) 不得同时运行 —— 互斥(半双工总线)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from pathlib import Path

# 让本脚本可独立运行：把 YuriArm 根加入 path 以 import yuriarm
_HERE = Path(__file__).resolve()
_ARM_ROOT = _HERE.parents[1]  # YuriArm/
if str(_ARM_ROOT) not in sys.path:
    sys.path.insert(0, str(_ARM_ROOT))

from yuriarm.config import DEFAULT_CONFIG_PATH, JOINT_NAMES, load_config  # noqa: E402
from yuriarm.leader_bridge import LeaderBridge  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("leader_remote")

# 默认 leader.json 路径
DEFAULT_LEADER_CONFIG = _ARM_ROOT / "configs" / "leader.json"


class _FakeLeader:
    """无硬件仿真主动臂：缓慢正弦摆动各关节，演示循环与安全。"""

    def __init__(self):
        import math
        self._t = 0.0
        self._math = math

    def get_action(self):
        self._t += 0.05
        m = self._math
        # 身体关节小范围摆动, gripper 开合
        swing = {f"{j}.pos": 30.0 * m.sin(self._t * m.pi) for j in JOINT_NAMES if j != "gripper"}
        swing["gripper.pos"] = 50.0 + 30.0 * m.sin(self._t * m.pi)
        return swing

    def disconnect(self):
        pass


class _MemoryTransport:
    """离线仿真传输：记录发送内容、不读回响应，用于 --mock 演示循环。"""

    def __init__(self):
        self.sent = []

    def send(self, obj):
        self.sent.append(obj)

    def recv(self, timeout_s=1.0):
        return None

    def close(self):
        pass


def _load_leader_conf(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"leader 配置不存在: {p}（可先用默认或改 --config）")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_leader(port: str, *, mock: bool):
    """惰性导入 lerobot SO101Leader，构造 leader。本机 lerobot 0.6.1 模块是 so_leader。"""
    if mock:
        return _FakeLeader()
    # 兼容不同 lerobot 版本：先试 so101_leader，再试 so_leader
    last_err: Exception | None = None
    for mod_name in ("lerobot.teleoperators.so101_leader", "lerobot.teleoperators.so_leader"):
        try:
            mod = __import__(mod_name, fromlist=["SO101Leader", "SOLeaderTeleopConfig"])
            leader_cls = getattr(mod, "SO101Leader", None) or getattr(mod, "SOLeader", None)
            cfg_cls = getattr(mod, "SOLeaderTeleopConfig", None) or getattr(mod, "SOLeaderConfig", None)
            if leader_cls is None:
                raise ImportError(f"{mod_name} 无 leader 类")
            cfg = cfg_cls(port=port, use_degrees=False)
            return leader_cls(cfg)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(
        f"无法导入 lerobot leader（试过 so101_leader/so_leader）: {last_err}\n"
        "请使用装有 lerobot 的 venv（本机: C:\\Users\\21209\\lerobot_venv312）"
    )


def _make_transport(link: str, args) -> "object":
    from yuriarm.esp32_transport import make_transport

    if link == "tcp":
        return make_transport("tcp", host=args.host, port=args.port)
    if link == "serial":
        return make_transport("serial", port=args.serial)
    raise ValueError(f"不支持的 link '{link}'")


def main() -> int:
    ap = argparse.ArgumentParser(description="主动臂遥控从动臂（经 ESP32 无线执行端）")
    ap.add_argument("--config", default=str(DEFAULT_LEADER_CONFIG), help="leader.json 路径")
    ap.add_argument("--leader-port", default=None, help="主动臂 USB 口（覆盖 config）")
    ap.add_argument("--link", default=None, choices=["tcp", "serial"], help="传输")
    ap.add_argument("--host", default="192.168.4.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--serial", default="COM18", help="USB 连 ESP32 的串口")
    ap.add_argument("--mock", action="store_true", help="无硬件: 仿真主动臂")
    ap.add_argument("--duration", type=float, default=3.0, help="--mock 演示时长(秒)")
    ap.add_argument("--check", action="store_true", help="只做连通检查并退出")
    args = ap.parse_args()

    conf = _load_leader_conf(args.config)
    leader_cfg = conf["leader"]
    link_cfg = conf.get("link", {})
    link = args.link or link_cfg.get("type", "tcp")
    leader_port = args.leader_port or leader_cfg.get("port", "COM7")

    # 关节限位复用 arm.json 的 safety.joint_limits（单一数据源）
    arm_cfg = load_config(DEFAULT_CONFIG_PATH)
    safety = arm_cfg.safety
    limits = {
        m: (float(safety["joint_limits"][m][0]), float(safety["joint_limits"][m][1]))
        for m in JOINT_NAMES
    }

    bridge = LeaderBridge(
        joint_limits=limits,
        max_velocity=float(leader_cfg.get("max_velocity", safety.get("max_velocity", 60.0))),
        deadband=float(leader_cfg.get("deadband", 0.5)),
        read_hz=float(leader_cfg.get("read_hz", 30.0)),
        send_hz=float(leader_cfg.get("send_hz", 10.0)),
        move_duration_s=float(leader_cfg.get("move_duration_s", 0.3)),
        estop_tolerance_s=float(leader_cfg.get("estop_tolerance_s", 1.0)),
        # 实时遥操作不限制速度：限速会让大幅快动时从动臂被拖累、跟不上/停住。
        # 限位仍在 joint_limits 里保证安全。若要保守可改 leader.json 打开。
        apply_speed_limit=bool(leader_cfg.get("apply_speed_limit", False)),
    )

    # 互斥提醒：小车与从动臂不可同时动（半双工总线）
    print("[leader_remote] 运行前确认: 小车(car_drive)未在运行！行驶期间从动臂不得动作。")

    leader = _make_leader(leader_port, mock=args.mock)
    mode = "仿真(mock)" if args.mock else f"真机 {leader_port}"
    # 连接主动臂（mock 无 connect 方法，跳过）
    connect = getattr(leader, "connect", None)
    if connect is not None:
        print(f"[leader_remote] 连接主动臂 {leader_port} ...")
        connect(calibrate=False)  # 用已有标定，不触发交互校准

    try:
        if args.mock:
            transport = _MemoryTransport()
        else:
            transport = _make_transport(link, args)
    except Exception as e:  # noqa: BLE001
        print(f"[leader_remote] 传输连接失败: {e}")
        return 1

    print(f"[leader_remote] 主动臂: {mode} | 链路: {link}")
    if args.check and not args.mock:
        transport.send({"cmd": "ping", "params": {}})
        resp = transport.recv(2.0)
        print(f"[leader_remote] ping 响应: {resp}")
        transport.close()
        return 0 if resp and resp.get("ok") else 1

    # 进入遥操作循环
    stop_event = threading.Event()
    if args.mock and args.duration:
        # 限时演示后自动结束
        def _timed_stop():
            import time
            time.sleep(args.duration)
            stop_event.set()

        threading.Thread(target=_timed_stop, daemon=True).start()
    try:
        bridge.run(leader, transport, stop_event=stop_event)
    except KeyboardInterrupt:
        print("\n[leader_remote] Ctrl+C -> estop")
        bridge.estop()
    finally:
        bridge.estop()
        try:
            transport.close()
            leader.disconnect()
        except Exception:  # noqa: BLE001
            pass
        print(f"[leader_remote] 已断开 (mock 发送 {len(getattr(transport,'sent',[]))} 帧)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

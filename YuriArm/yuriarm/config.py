"""配置中心：默认值 + 用户 JSON 深度合并 + 姿态持久化。

所有可调参数集中在 DEFAULT_CONFIG，避免把魔法数字散落在业务代码里。
用户配置写在 YuriArm/configs/arm.json（首次运行自动生成），
`yuriarm teach <pose>` 会把当前关节角写回该文件。
"""
from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "arm.json"

# SO-101 follower 6 个关节名（与 lerobot so101_follower 一致）
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

DEFAULT_JOINT_LIMITS: dict[str, tuple[float, float]] = {m: (-100.0, 100.0) for m in JOINT_NAMES}

# 归一化单位约定（与 lerobot so101_follower 默认 use_degrees=False 一致）：
# 身体关节 -100..100（对应标定范围），gripper 0..100。
# gripper 开/合方向取决于装配与标定，首次上机用 `yuriarm gripper open/close` 校核方向。
DEFAULT_CONFIG: dict[str, Any] = {
    "arm": {
        "port": "COM7",
        "id": "zgq_follower_arm",
        "use_degrees": False,
        "disable_torque_on_disconnect": True,
        # 连接后按"电机名 -> {寄存器: 值}"覆盖保护参数（不动 lerobot 源码）。
        # 背景：STS3215 的 Overload_Torque 是 1 字节寄存器（×8≈实际负载阈值）。
        # 身体关节出厂/lerobot 默认 80（≈负载640）、夹爪 25（≈200），这是 7.4V 工况的；
        # 5V 下负载读数虚高（正常运行 1050~1250），远超阈值 → 一运动就硬件过载锁死
        # （需断电才能复位）。统一调到 200（≈负载1600：高于 5V 正常值，低于堵转 2047）。
        # 真碰撞保护改由软件急停（safety.estop_load，可恢复无需断电）承担。
        # 7.4V 供电时可按需改回 {"Overload_Torque": 80} 等原值。
        "motor_overrides": {
            "shoulder_pan": {"Overload_Torque": 200},
            "shoulder_lift": {"Overload_Torque": 200},
            "elbow_flex": {"Overload_Torque": 200},
            "wrist_flex": {"Overload_Torque": 200},
            "wrist_roll": {"Overload_Torque": 200},
            "gripper": {"Overload_Torque": 200},
        },
    },
    "safety": {
        # 归一化单位/秒；插值步频
        "max_velocity": 60.0,
        "move_steps_hz": 20.0,
        # 急停负载阈值（Present_Load 绝对值，超过即停，软件可恢复）。可为 float（全局）或
        # dict：{"default": 全局, "<关节>": 覆盖}。5V 下正常运行负载 ~1050-1250，故用 1500
        # （高于正常、低于堵转 2047）；7.4V 下可调回 ~800。
        "estop_load": {"default": 1500.0, "gripper": 1500.0},
        "joint_limits": {m: list(v) for m, v in DEFAULT_JOINT_LIMITS.items()},
    },
    "gripper": {
        "open": 100.0,           # 张开目标（0..100，方向按上机校核调整）
        "close": 0.0,            # 合拢目标
        "close_step": 2.0,       # 合拢轮询步进
        "close_interval_s": 0.05,  # 合拢轮询间隔
        "close_max_load": 450.0,   # 合拢中负载超过即判定"夹住"（硬压快速通道）
        "close_confirm_load": 250.0,   # 位置停滞时，继续压、负载超过此值=确认夹住（5V 下空转峰值~228，须高于它）
        "close_confirm_time_s": 1.5,   # 停滞确认窗口：压这么久负载仍低于 confirm_load → 判定没夹到
        "close_timeout_s": 4.0,    # 合拢超时（未检测到负载=没夹到）
        "close_velocity": 20.0,    # 合拢阶段限速
    },
    "pick": {
        # M0：示教-回放拾取周期使用的姿态名（见 docs/方案设计.md §2.1 / §4.4）
        "pick_high_pose": "pick_high",   # 目标正上方、夹爪张开
        "pick_low_pose": "pick_low",     # 下压到位、手指套住方块
        "drop_pose": "drop",             # 料篮正上方
        "max_retries": 2,
        # M1+ 任务空间参数（接入 FK/IK 与相机后使用，见 planner.py）
        "approach_z_mm": 70.0,     # 高空转移高度
        "descend_gap_mm": 3.0,     # 下压到位时手指底与方块顶面的间隙
        "lift_z_mm": 70.0,
        "transit_z_mm": 80.0,
        "drop_z_mm": 60.0,
    },
    "blocks": {
        "cube_size_mm": 30.0,
        "target_colors": ["red", "blue"],
        "scores": {"red": 1, "blue": 1, "green": 1, "yellow": 1, "orange": 1, "purple": 1},
        "min_gap_mm": 3.0,          # 判定"紧贴/跳过"的最小缝隙
        "drop_zone_mm": {"x": 200.0, "y": -200.0},
    },
    "poses": {
        "home": {m: 0.0 for m in JOINT_NAMES},
        "pick_high": {},
        "pick_low": {},
        "drop": {},
    },
    "server": {"host": "127.0.0.1", "port": 8765},
    "perception": {
        "enabled": False,
        "camera_index": 1,
        "homography_path": None,   # 由 tools/calib_homography.py 生成
        "ml_weights": None,        # YuriEye ml/weights/best.pt
        "ml_conf": 0.25,
        "cube_min_area_px": 400.0,
        "yurieye_path": None,      # None=自动探测 YuriEye 目录
    },
}

_CONFIG_LOCK = threading.RLock()


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 非空值覆盖 base；保持 base 中未出现的键。"""
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass
class ArmConfig:
    """YuriArm 运行配置（内存态），由 :func:`load_config` 构造。"""

    data: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_CONFIG))
    path: Path | None = None

    # ---- 便捷访问器（保持单一数据源，避免重复解析） ----
    @property
    def arm(self) -> dict[str, Any]:
        return self.data["arm"]

    @property
    def safety(self) -> dict[str, Any]:
        return self.data["safety"]

    @property
    def gripper(self) -> dict[str, Any]:
        return self.data["gripper"]

    @property
    def pick(self) -> dict[str, Any]:
        return self.data["pick"]

    @property
    def blocks(self) -> dict[str, Any]:
        return self.data["blocks"]

    @property
    def poses(self) -> dict[str, dict[str, float]]:
        return self.data["poses"]

    @property
    def server(self) -> dict[str, Any]:
        return self.data["server"]

    @property
    def perception(self) -> dict[str, Any]:
        return self.data["perception"]

    @property
    def joint_limits(self) -> dict[str, tuple[float, float]]:
        return {
            m: (float(lo), float(hi))
            for m, (lo, hi) in self.safety["joint_limits"].items()
        }

    def get_pose(self, name: str) -> dict[str, float]:
        """返回命名姿态的关节角副本；不存在时抛 KeyError。"""
        try:
            return dict(self.poses[name])
        except KeyError:
            raise KeyError(f"姿态 '{name}' 未定义（可用: {sorted(self.poses)}）") from None

    def set_pose(self, name: str, joints: dict[str, float]) -> None:
        """写入/覆盖命名姿态并立即持久化。"""
        unknown = set(joints) - set(JOINT_NAMES)
        if unknown:
            raise ValueError(f"未知关节: {sorted(unknown)}（合法: {JOINT_NAMES}）")
        self.poses[name] = {m: float(joints.get(m, 0.0)) for m in JOINT_NAMES}
        self.save()

    # ---- 持久化 ----
    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path) if path else (self.path or DEFAULT_CONFIG_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _CONFIG_LOCK:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        self.path = p
        return p

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path | None = None) -> "ArmConfig":
        merged = _deep_merge(DEFAULT_CONFIG, data or {})
        return cls(data=merged, path=path)


def load_config(path: str | Path | None = None, *, create_if_missing: bool = True) -> ArmConfig:
    """加载配置：默认值 + 用户文件深合并。

    create_if_missing=True 时，若文件不存在则写入默认配置（含默认姿态），方便 `teach` 直接修改。
    """
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if p.is_file():
        with _CONFIG_LOCK:
            with open(p, "r", encoding="utf-8") as f:
                user = json.load(f)
        return ArmConfig.from_dict(user, path=p)

    cfg = ArmConfig.from_dict({}, path=p)
    if create_if_missing:
        cfg.save(p)
    return cfg

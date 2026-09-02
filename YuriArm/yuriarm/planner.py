"""任务空间抓取规划（与相机 / 运动学解耦）。

- :class:`Block`：桌面 mm 系下的目标方块（x, y, 颜色, 顶面 z）。
- :class:`PlanPoint` / :class:`PickPlan`：一次抓取的任务空间路径
  （approach → descend → close → lift → transit → drop）。
- :class:`PickPlanner`：顺序决策（高分先保 / 紧贴先清 / 风险后置）与路径生成。
- :class:`Kinematics`：关节↔任务空间转换接口；当前只提供 2D 可达性近似，
  完整的 SO-101 FK/IK 需要在真机标定后接入（docs/方案设计.md M1，见 TODO）。

设计目标：M0 用示教-回放姿态（arm.pick）跑通；相机与 FK/IK 到位后，
state_machine 只需把 PickPlan 交给已实现的 Kinematics 即可无缝切换，无需改动规划逻辑。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .config import ArmConfig


@dataclass
class Block:
    """桌面 mm 系下的一个方块。"""

    x_mm: float
    y_mm: float
    color: str
    z_mm: float = 30.0          # 顶面高度（立方体坐于桌面时 = cube_size）
    score: float = 1.0
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "x_mm": round(self.x_mm, 2),
            "y_mm": round(self.y_mm, 2),
            "z_mm": round(self.z_mm, 2),
            "color": self.color,
            "score": self.score,
            "label": self.label,
        }


class KinematicsUnavailableError(NotImplementedError):
    """SO-101 正向/逆向运动学尚未标定接入（M1 前置项）。"""


class Kinematics:
    """关节↔任务空间转换接口。

    默认实现只做 2D 平面可达性近似；joints_from_task 明确抛错，
    避免调用方在未标定 FK/IK 时"看似可用实则乱动"。接入真机标定后的
    FK/IK 时子类覆盖这两个方法即可，上层（planner/state_machine）不用改。
    """

    @property
    def available(self) -> bool:
        return False

    def is_reachable(self, x_mm: float, y_mm: float, z_mm: float) -> bool:
        raise KinematicsUnavailableError(
            "未接入 SO-101 运动学（需要 M1 真机标定 FK/IK）。当前请使用示教-回放模式（arm.pick）。"
        )

    def joints_from_task(self, x_mm: float, y_mm: float, z_mm: float, yaw_deg: float, seed=None) -> dict[str, float] | None:
        raise KinematicsUnavailableError(
            "未接入 SO-101 运动学（需要 M1 真机标定 FK/IK）。当前请使用示教-回放模式（arm.pick）。"
        )


class PlanPoint:
    """任务空间路径点（gripper 目标位姿 + 夹爪动作）。"""

    __slots__ = ("x_mm", "y_mm", "z_mm", "yaw_deg", "gripper", "label")

    def __init__(self, x_mm: float, y_mm: float, z_mm: float, yaw_deg: float = 0.0,
                 gripper: str | None = None, label: str = ""):
        self.x_mm = float(x_mm)
        self.y_mm = float(y_mm)
        self.z_mm = float(z_mm)
        self.yaw_deg = float(yaw_deg)
        self.gripper = gripper      # None=不变, "open", "close"
        self.label = label

    def to_dict(self) -> dict[str, Any]:
        return {
            "x_mm": round(self.x_mm, 2),
            "y_mm": round(self.y_mm, 2),
            "z_mm": round(self.z_mm, 2),
            "yaw_deg": round(self.yaw_deg, 2),
            "gripper": self.gripper,
            "label": self.label,
        }

    def distance_to(self, other: "PlanPoint") -> float:
        return math.hypot(self.x_mm - other.x_mm, self.y_mm - other.y_mm, self.z_mm - other.z_mm)


@dataclass
class PickPlan:
    """一次抓取的任务空间路径。"""

    block: Block
    points: list[PlanPoint] = field(default_factory=list)
    reachable: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "block": self.block.to_dict(),
            "reachable": self.reachable,
            "reason": self.reason,
            "points": [p.to_dict() for p in self.points],
        }


def _distance_xy(a: Block, b: Block) -> float:
    return math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm)


class PickPlanner:
    """按设计文档 §4.2/§4.3 生成抓取顺序与路径。"""

    def __init__(self, config: ArmConfig, kinematics: Kinematics | None = None):
        self.config = config
        self.kinematics = kinematics or Kinematics()
        self.cube_size_mm = float(config.blocks.get("cube_size_mm", 30.0))
        self.min_gap_mm = float(config.blocks.get("min_gap_mm", 3.0))
        drop = config.blocks.get("drop_zone_mm", {"x": 200.0, "y": -200.0})
        self.drop_zone = (float(drop["x"]), float(drop["y"]))
        p = config.pick
        self.approach_z_mm = float(p.get("approach_z_mm", 70.0))
        self.descend_gap_mm = float(p.get("descend_gap_mm", 3.0))
        self.lift_z_mm = float(p.get("lift_z_mm", 70.0))
        self.transit_z_mm = float(p.get("transit_z_mm", 80.0))
        self.drop_z_mm = float(p.get("drop_z_mm", 60.0))

    # ------------------------------------------------------------- 顺序决策
    def target_blocks(self, blocks: list[Block], target_colors: list[str] | None = None) -> list[Block]:
        """过滤出目标色方块并打分。"""
        targets = set(target_colors or self.config.blocks.get("target_colors", []))
        scores = self.config.blocks.get("scores", {})
        out: list[Block] = []
        for b in blocks:
            if b.color in targets:
                # 配置分值优先，未配置时保留 Block 自带分值
                b.score = float(scores.get(b.color, b.score))
                out.append(b)
        return out

    def order_blocks(self, blocks: list[Block], target_colors: list[str] | None = None) -> list[Block]:
        """抓取顺序：按价值降序；同价值先清"紧贴目标"（腾缝），再按风险升序。"""
        targets = self.target_blocks(blocks, target_colors)
        cube = self.cube_size_mm
        min_gap = self.min_gap_mm

        def tightness(b: Block) -> int:
            # 与其它方块（含非目标）贴得越紧越先处理，为后续腾缝
            return sum(1 for o in blocks if o is not b and _distance_xy(b, o) < cube + min_gap)

        def risk(b: Block) -> float:
            others = [o for o in blocks if o is not b]
            if not others:
                return -1.0
            return min(_distance_xy(b, o) for o in others)

        return sorted(
            targets,
            key=lambda b: (-b.score, -tightness(b), risk(b)),
        )

    def nearest_order(self, blocks: list[Block], current: tuple[float, float] | None = None) -> list[Block]:
        """近邻贪心排序：减少转移距离（可选，用于路线优化）。"""
        remaining = list(blocks)
        ordered: list[Block] = []
        cur = current or (0.0, 0.0)
        while remaining:
            nxt = min(remaining, key=lambda b: math.hypot(b.x_mm - cur[0], b.y_mm - cur[1]))
            ordered.append(nxt)
            cur = (nxt.x_mm, nxt.y_mm)
            remaining.remove(nxt)
        return ordered

    # ------------------------------------------------------------- 路径生成
    def plan_pick(self, block: Block) -> PickPlan:
        """为单个方块生成任务空间路径（"高空过、垂直落"，设计文档 §4.3）。"""
        plan = PickPlan(block=block)
        # 手指底 = 方块顶面 - 方块高 + gap（手指底与桌面之间留 descend_gap）
        dz = self.cube_size_mm
        descend_z = max(self.descend_gap_mm, block.z_mm - dz + self.descend_gap_mm)
        plan.points = [
            PlanPoint(block.x_mm, block.y_mm, self.approach_z_mm, gripper="open", label="approach"),
            PlanPoint(block.x_mm, block.y_mm, descend_z, gripper=None, label="descend"),
            PlanPoint(block.x_mm, block.y_mm, descend_z, gripper="close", label="close"),
            PlanPoint(block.x_mm, block.y_mm, self.lift_z_mm, gripper=None, label="lift"),
            PlanPoint(self.drop_zone[0], self.drop_zone[1], self.transit_z_mm, gripper=None, label="transit"),
            PlanPoint(self.drop_zone[0], self.drop_zone[1], self.drop_z_mm, gripper="open", label="drop"),
        ]
        try:
            for pt in plan.points:
                if not self.kinematics.is_reachable(pt.x_mm, pt.y_mm, pt.z_mm):
                    plan.reachable = False
                    plan.reason = f"路径点不可达: {pt.label} ({pt.x_mm:.0f},{pt.y_mm:.0f},{pt.z_mm:.0f})"
                    break
        except KinematicsUnavailableError:
            # 未接入运动学：不阻塞路径生成，执行阶段回退示教-回放（state_machine 处理）
            plan.reason = "kinematics unavailable: 执行阶段将回退示教-回放模式"
        return plan

    def plan_batch(
        self,
        blocks: list[Block],
        target_colors: list[str] | None = None,
        *,
        nearest: bool = False,
    ) -> list[PickPlan]:
        """批量规划：先决策顺序，再逐块生成路径。"""
        ordered = self.order_blocks(blocks, target_colors)
        if nearest:
            ordered = self.nearest_order(ordered)
        return [self.plan_pick(b) for b in ordered]

"""抓取任务状态机：SCAN → PLAN → EXECUTE → VERIFY（设计文档 §4.4）。

- SCAN：感知扫描桌面（无感知 → 使用调用方传入的手动 blocks = 手动模式）
- PLAN：排序（高分先保/紧贴先清）+ 逐块生成任务空间路径
- EXECUTE：逐块执行；当前使用示教-回放（arm.pick）；接入 FK/IK 后
  自动切换为按 PickPlan 关节路径执行（planner.Kinematics）
- VERIFY：感知复查（可选）：目标消失、其它方块未动

每颗方块独立容错：失败重试 ≤ max_retries；整体返回结构化报告。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .arm import YuriArm
from .config import ArmConfig
from .perception import Perception, PerceptionUnavailable
from .planner import Block, PickPlanner


@dataclass
class TaskReport:
    """一次抓取任务的结构化结果。"""

    records: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"records": self.records, "summary": self.summary}


class TaskExecutor:
    """完整抓取任务执行器（可被 CLI/server/测试复用）。"""

    def __init__(self, arm: YuriArm, config: ArmConfig,
                 perception: Perception | None = None,
                 planner: PickPlanner | None = None):
        self.arm = arm
        self.config = config
        self.perception = perception
        self.planner = planner or PickPlanner(config)

    # ------------------------------------------------------------- 入口
    def run(self, *, target_colors: list[str] | None = None,
            blocks: list[Block] | None = None,
            verify: bool = True) -> TaskReport:
        report = TaskReport()
        try:
            scanned = self._scan()
        except PerceptionUnavailable as e:
            if blocks is None:
                report.records.append({"phase": "scan", "error": str(e)})
                report.summary = {"succeeded": 0, "failed": 1, "skipped": 0,
                                  "score": 0.0, "detail": "感知不可用且未提供手动 blocks"}
                return report
            scanned = blocks
        if not scanned:
            report.summary = {"succeeded": 0, "failed": 0, "skipped": 0, "score": 0.0,
                              "detail": "扫描未发现任何方块"}
            return report

        plans = self.planner.plan_batch(scanned, target_colors)
        if not plans:
            report.summary = {"succeeded": 0, "failed": 0, "skipped": 0, "score": 0.0,
                              "detail": f"目标色方块为空（目标: {target_colors or self.config.blocks.get('target_colors')}）"}
            return report

        max_retries = int(self.config.pick.get("max_retries", 2))
        succeeded = failed = skipped = 0
        score = 0.0
        picked_blocks: list[Block] = []
        for plan in plans:
            rec: dict[str, Any] = {"block": plan.block.to_dict(), "retries": 0, "ok": False}
            if not plan.reachable:
                rec["error"] = plan.reason or "不可达"
                skipped += 1
                report.records.append(rec)
                continue
            attempt = 0
            last_err = ""
            while attempt <= max_retries:
                try:
                    result = self._execute_plan(plan)
                    rec["result"] = result
                    rec["ok"] = True
                    succeeded += 1
                    score += plan.block.score
                    picked_blocks.append(plan.block)
                    break
                except Exception as e:  # noqa: BLE001 —— 单颗失败不中断整批
                    last_err = f"{type(e).__name__}: {e}"
                    attempt += 1
                    rec["retries"] = attempt
            if not rec["ok"]:
                rec["error"] = last_err
                failed += 1
            report.records.append(rec)

        verify_result: dict[str, Any] | None = None
        if verify and picked_blocks and self.perception is not None:
            try:
                current = self.perception.scan_blocks()
                moved = []
                for b in picked_blocks:
                    v = _verify_one(self.perception, scanned, current, b)
                    if not v["ok"]:
                        moved.append({"block": b.to_dict(), "detail": v})
                verify_result = {"rescanned_blocks": len(current), "issues": moved}
                if moved:
                    rec_v = {"phase": "verify", "error": "部分目标未移除或其它方块移动", "detail": moved}
                    report.records.append(rec_v)
                    failed += 1
            except PerceptionUnavailable as e:
                verify_result = {"error": str(e)}

        report.summary = {
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "score": round(score, 2),
            "target_count": len(plans),
            "verify": verify_result,
        }
        return report

    # ------------------------------------------------------------- 内部
    def _scan(self) -> list[Block]:
        if self.perception is None:
            raise PerceptionUnavailable("未配置感知")
        return self.perception.scan_blocks()

    def _execute_plan(self, plan) -> dict[str, Any]:
        """执行单个 PickPlan：有可用运动学则按关节路径执行，否则回退示教-回放。"""
        kin = self.planner.kinematics
        if kin.available:
            joints = self._plan_to_joint_path(kin, plan)
            return self._execute_joint_path(joints)
        # 回退：M0 示教-回放（需要 config 中已 teach 的 pick_high/pick_low/drop）
        result = self.arm.pick()
        if not result.get("ok"):
            raise RuntimeError(result.get("reason") or "拾取失败（未夹住）")
        return result

    def _plan_to_joint_path(self, kin, plan) -> list[dict[str, float]]:
        path = []
        seed = None
        for pt in plan.points:
            j = kin.joints_from_task(pt.x_mm, pt.y_mm, pt.z_mm, pt.yaw_deg, seed=seed)
            if j is None:
                raise RuntimeError(f"IK 无解 at {pt.label}")
            seed = j
            path.append(j)
        return path

    def _execute_joint_path(self, path: list[dict[str, float]]) -> dict[str, Any]:
        steps = []
        for j in path:
            self.arm.move_joints(j)
            steps.append({"joints": j})
        return {"mode": "joint_path", "steps": steps}


def _verify_one(perception: Perception, initial: list[Block], current: list[Block],
                picked: Block) -> dict[str, Any]:
    from .perception import verify_pick
    return verify_pick(initial, current, picked)

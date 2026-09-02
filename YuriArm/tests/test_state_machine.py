import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.arm import YuriArm  # noqa: E402
from yuriarm.config import ArmConfig  # noqa: E402
from yuriarm.perception import Perception  # noqa: E402
from yuriarm.planner import Block, PickPlanner  # noqa: E402
from yuriarm.state_machine import TaskExecutor  # noqa: E402

POSES = {
    "home": {m: 0.0 for m in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]},
    "pick_high": {"shoulder_pan": 0.0, "shoulder_lift": -40.0, "elbow_flex": 40.0,
                  "wrist_flex": 0.0, "wrist_roll": 0.0, "gripper": 100.0},
    "pick_low": {"shoulder_pan": 0.0, "shoulder_lift": -20.0, "elbow_flex": 20.0,
                 "wrist_flex": 0.0, "wrist_roll": 0.0, "gripper": 100.0},
    "drop": {"shoulder_pan": 40.0, "shoulder_lift": -30.0, "elbow_flex": 30.0,
             "wrist_flex": 0.0, "wrist_roll": 0.0, "gripper": 100.0},
}


class FakePerception(Perception):
    """可编程感知：每次 scan_blocks 从响应队列取一帧（首次=初始地图，之后=验证地图）。"""

    def __init__(self, cfg, responses):
        super().__init__(cfg)
        self._responses = list(responses)

    def scan_blocks(self):
        if not self._responses:
            return []
        return self._responses.pop(0)


def make_arm_with_block(blocked=True):
    cfg = ArmConfig.from_dict({"poses": POSES, "pick": {"max_retries": 0}})
    arm = YuriArm(cfg, mock=True)
    arm.connect()
    if blocked:
        arm.backend.set_block(True)
    return arm, cfg


class TestStateMachine(unittest.TestCase):
    def test_run_with_perception_success(self):
        arm, cfg = make_arm_with_block()
        init = [Block(x_mm=100, y_mm=100, color="red", score=1)]
        perception = FakePerception(cfg, [init, []])  # 第二次扫描=验证：目标已移除
        ex = TaskExecutor(arm, cfg, perception=perception, planner=PickPlanner(cfg))
        report = ex.run(target_colors=["red"])
        self.assertEqual(report.summary["succeeded"], 1, str(report.to_dict()))
        self.assertEqual(report.summary["failed"], 0)
        self.assertEqual(report.summary["score"], 1.0)

    def test_run_filters_target_color(self):
        arm, cfg = make_arm_with_block()
        init = [
            Block(x_mm=100, y_mm=100, color="red", score=1),
            Block(x_mm=300, y_mm=300, color="blue", score=1),
        ]
        perception = FakePerception(cfg, [init, []])
        ex = TaskExecutor(arm, cfg, perception=perception, planner=PickPlanner(cfg))
        report = ex.run(target_colors=["red"])
        self.assertEqual(report.summary["target_count"], 1)
        self.assertEqual(report.records[0]["block"]["color"], "red")

    def test_run_with_manual_blocks(self):
        arm, cfg = make_arm_with_block()
        ex = TaskExecutor(arm, cfg, perception=None, planner=PickPlanner(cfg))
        report = ex.run(target_colors=["red"], blocks=[Block(x_mm=10, y_mm=10, color="red")])
        self.assertEqual(report.summary["succeeded"], 1)

    def test_run_without_perception_or_blocks(self):
        arm, cfg = make_arm_with_block(blocked=False)
        ex = TaskExecutor(arm, cfg, perception=None, planner=PickPlanner(cfg))
        report = ex.run(target_colors=["red"])
        self.assertEqual(report.summary["succeeded"], 0)
        self.assertEqual(report.summary["failed"], 1)
        self.assertIn("感知不可用", report.summary["detail"])

    def test_run_pick_failure_reported(self):
        arm, cfg = make_arm_with_block(blocked=False)  # 无方块 → 夹取失败
        ex = TaskExecutor(arm, cfg, perception=None, planner=PickPlanner(cfg))
        report = ex.run(target_colors=["red"], blocks=[Block(x_mm=10, y_mm=10, color="red")])
        self.assertEqual(report.summary["failed"], 1)
        self.assertFalse(report.records[0]["ok"])
        self.assertIn("夹取失败", report.records[0]["error"])


if __name__ == "__main__":
    unittest.main()

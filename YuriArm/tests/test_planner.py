import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.config import ArmConfig  # noqa: E402
from yuriarm.planner import (  # noqa: E402
    Block,
    Kinematics,
    KinematicsUnavailableError,
    PickPlanner,
)


def make_planner(**overrides):
    data = {}
    if overrides:
        data.update(overrides)
    cfg = ArmConfig.from_dict(data)
    return PickPlanner(cfg)


SCORES = {"blocks": {"scores": {"red": 1, "blue": 3, "green": 1}}}


def blocks():
    return [
        Block(x_mm=10, y_mm=10, color="red", score=1),
        Block(x_mm=20, y_mm=10, color="blue", score=3),
        Block(x_mm=200, y_mm=200, color="green", score=1),
    ]


class TestPlannerOrder(unittest.TestCase):
    def test_order_high_score_first(self):
        pl = make_planner(**SCORES)
        ordered = pl.order_blocks(blocks(), target_colors=["red", "blue"])
        self.assertEqual([b.color for b in ordered], ["blue", "red"])

    def test_target_filter(self):
        pl = make_planner()
        ordered = pl.order_blocks(blocks(), target_colors=["red"])
        self.assertEqual([b.color for b in ordered], ["red"])

    def test_tight_blocks_first_among_same_score(self):
        # 同分时：紧贴其他方块的先清（腾缝）
        a = Block(x_mm=0, y_mm=0, color="red", score=1)
        b = Block(x_mm=0, y_mm=31, color="red", score=1)   # 紧贴 a（30mm 方块 + 1mm 缝）
        c = Block(x_mm=300, y_mm=300, color="red", score=1)  # 孤立
        pl = make_planner()
        ordered = pl.order_blocks([a, b, c], target_colors=["red"])
        # a/b 紧贴彼此 → 应排在 c 之前
        self.assertLess(ordered.index(a), ordered.index(c))
        self.assertLess(ordered.index(b), ordered.index(c))

    def test_nearest_order(self):
        pl = make_planner()
        bs = [
            Block(x_mm=100, y_mm=0, color="red"),
            Block(x_mm=0, y_mm=0, color="red"),
            Block(x_mm=50, y_mm=50, color="red"),
        ]
        ordered = pl.nearest_order(bs, current=(0, 0))
        self.assertEqual(ordered[0].x_mm, 0)
        self.assertEqual(ordered[1].x_mm, 50)
        self.assertEqual(ordered[2].x_mm, 100)


class TestPlannerPath(unittest.TestCase):
    def test_plan_pick_sequence(self):
        pl = make_planner()
        plan = pl.plan_pick(Block(x_mm=100, y_mm=50, color="red", z_mm=30))
        labels = [p.label for p in plan.points]
        self.assertEqual(labels, ["approach", "descend", "close", "lift", "transit", "drop"])
        # 高空过、垂直落
        self.assertEqual(plan.points[0].x_mm, 100)
        self.assertEqual(plan.points[0].z_mm, pl.approach_z_mm)
        self.assertEqual(plan.points[1].x_mm, 100)
        self.assertEqual(plan.points[1].z_mm, 3.0)  # 30-30+3
        self.assertEqual(plan.points[2].gripper, "close")
        self.assertEqual(plan.points[5].gripper, "open")
        self.assertEqual(plan.points[4].x_mm, pl.drop_zone[0])

    def test_kinematics_unavailable_by_default(self):
        kin = Kinematics()
        self.assertFalse(kin.available)
        with self.assertRaises(KinematicsUnavailableError):
            kin.is_reachable(10, 10, 10)

    def test_plan_batch(self):
        pl = make_planner(**SCORES)
        plans = pl.plan_batch(blocks(), target_colors=["blue", "red"])
        self.assertEqual([p.block.color for p in plans], ["blue", "red"])


if __name__ == "__main__":
    unittest.main()

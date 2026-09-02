import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.arm import ArmEStopError, ArmError, MockArm, YuriArm  # noqa: E402
from yuriarm.config import ArmConfig as RealArmConfig  # noqa: E402


def make_config(**overrides):
    data = {}
    data.update(overrides)
    return RealArmConfig.from_dict(data)


POSES = {
    "home": {m: 0.0 for m in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]},
    "pick_high": {"shoulder_pan": 0.0, "shoulder_lift": -40.0, "elbow_flex": 40.0,
                  "wrist_flex": 0.0, "wrist_roll": 0.0, "gripper": 100.0},
    "pick_low": {"shoulder_pan": 0.0, "shoulder_lift": -20.0, "elbow_flex": 20.0,
                 "wrist_flex": 0.0, "wrist_roll": 0.0, "gripper": 100.0},
    "drop": {"shoulder_pan": 40.0, "shoulder_lift": -30.0, "elbow_flex": 30.0,
             "wrist_flex": 0.0, "wrist_roll": 0.0, "gripper": 100.0},
}


class TestMockArm(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(poses=POSES)
        self.arm = YuriArm(self.cfg, mock=True)

    def test_connect_and_move(self):
        self.arm.connect()
        self.assertTrue(self.arm.is_connected())
        result = self.arm.move_joints({"shoulder_lift": 30.0, "gripper": 50.0}, duration=0.2)
        self.assertAlmostEqual(result["shoulder_lift"], 30.0, places=1)
        self.assertAlmostEqual(result["gripper"], 50.0, places=1)

    def test_move_without_connect_raises(self):
        with self.assertRaises(Exception):
            self.arm.move_joints({"shoulder_lift": 10.0})

    def test_limit_violation_rejected(self):
        self.arm.connect()
        with self.assertRaises(ArmError):
            self.arm.move_joints({"shoulder_lift": 500.0})

    def test_unknown_joint_rejected(self):
        self.arm.connect()
        with self.assertRaises(ArmError):
            self.arm.move_joints({"bogus": 1.0})

    def test_estop_interrupts_move(self):
        self.arm.connect()
        calls = {"n": 0}

        def stop_on_first_step(_pos):
            calls["n"] += 1
            if calls["n"] == 1:
                self.arm.estop()

        with self.assertRaises(ArmEStopError):
            self.arm.move_joints({"shoulder_lift": 80.0}, duration=1.0, on_step=stop_on_first_step)
        self.assertEqual(self.arm.state, "estop")

    def test_estop_resume_cycle(self):
        self.arm.connect()
        self.arm.estop()
        self.assertFalse(self.arm.is_connected())
        self.arm.resume()
        self.assertTrue(self.arm.is_connected())

    def test_close_gripper_gripped_with_block(self):
        self.arm.connect()
        self.arm.backend.set_block(True)
        # 先张开再合拢，确保有合拢行程
        self.arm.open_gripper()
        result = self.arm.close_gripper(max_load=200.0, timeout=2.0)
        self.assertEqual(result["result"], "gripped")
        self.assertGreater(result["load"], 200.0)

    def test_close_gripper_timeout_without_block(self):
        self.arm.connect()
        self.arm.open_gripper()
        result = self.arm.close_gripper(max_load=200.0, timeout=1.0)
        self.assertEqual(result["result"], "timeout")

    def test_pick_cycle_ok_with_block(self):
        self.arm.connect()
        self.arm.backend.set_block(True)
        result = self.arm.pick()
        self.assertTrue(result["ok"], str(result))
        labels = [s["step"] for s in result["steps"]]
        self.assertEqual(labels, ["approach", "descend", "close", "lift", "transit", "drop"])

    def test_pick_fails_without_block(self):
        self.arm.connect()
        result = self.arm.pick()
        self.assertFalse(result["ok"])
        self.assertIn("夹取失败", result["reason"])

    def test_record_pose_persists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = RealArmConfig.from_dict({}, path=Path(td) / "arm.json")
            arm = YuriArm(cfg, mock=True)
            arm.connect()
            arm.move_joints({"shoulder_lift": 25.0}, duration=0.1)
            joints = arm.record_pose("custom")
            self.assertEqual(joints["shoulder_lift"], 25.0)
            reloaded = RealArmConfig.from_dict(
                __import__("json").loads((Path(td) / "arm.json").read_text(encoding="utf-8")),
                path=Path(td) / "arm.json",
            )
            self.assertEqual(reloaded.poses["custom"]["shoulder_lift"], 25.0)

    def test_telemetry(self):
        self.arm.connect()
        t = self.arm.read_telemetry()
        self.assertIn("positions", t)
        self.assertIn("loads", t)
        self.assertIn("voltage", t)

    def test_status(self):
        self.arm.connect()
        s = self.arm.status()
        self.assertEqual(s["backend"], "mock")
        self.assertTrue(s["connected"])


if __name__ == "__main__":
    unittest.main()

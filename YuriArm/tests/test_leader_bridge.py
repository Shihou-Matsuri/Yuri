"""leader_bridge 无硬件测试。

用 FakeLeader / FakeTransport 验证映射、死区、限速、限位、急停、断连逻辑。
运行：python -m unittest discover -s YuriArm/tests -v
"""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.config import JOINT_NAMES  # noqa: E402
from yuriarm.leader_bridge import LeaderBridge  # noqa: E402

# 默认：全身关节 -100..100，gripper 0..100
DEFAULT_LIMITS = {m: (-100.0, 100.0) for m in JOINT_NAMES}


def make_bridge(**kw) -> LeaderBridge:
    defaults = dict(
        joint_limits=DEFAULT_LIMITS,
        max_velocity=60.0,
        deadband=0.5,
        cmd_name="teleop_joints",
        read_hz=10.0,
        send_hz=10.0,
        estop_tolerance_s=1.0,
    )
    defaults.update(kw)
    return LeaderBridge(**defaults)


def full_action(**overrides) -> dict[str, float]:
    """合法 6 关节 .pos 读数。"""
    a = {f"{m}.pos": 0.0 for m in JOINT_NAMES}
    a.update({f"{k}.pos" if not k.endswith(".pos") else k: v for k, v in overrides.items()})
    return a


class FakeLeader:
    def __init__(self):
        self.action = full_action()
        self.calls = 0
        self.fail = False  # True -> get_action 抛异常

    def get_action(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("模拟断连")
        return dict(self.action)

    def disconnect(self):
        pass


class FakeTransport:
    def __init__(self):
        self.sent = []

    def send(self, obj):
        self.sent.append(obj)

    def recv(self, timeout_s=1.0):
        return None

    def close(self):
        pass


class TestMapAndClip(unittest.TestCase):
    def test_strips_pos_suffix_and_clips_to_limits(self):
        bridge = make_bridge(joint_limits={
            **DEFAULT_LIMITS,
            "shoulder_lift": (-38.0, 60.0),  # 窄范围
        })
        # 通过 step 验证：shoulder_lift 给 200 -> 应被截到 60
        leader = FakeLeader()
        leader.action = full_action(shoulder_lift=200.0)
        t = FakeTransport()
        out = bridge.step(leader, t)
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out["shoulder_lift"], 60.0)
        self.assertEqual(out["shoulder_pan"], 0.0)

    def test_unknown_keys_ignored(self):
        bridge = make_bridge()
        leader = FakeLeader()
        leader.action = {"unknown_joint.pos": 42.0, **full_action()}
        t = FakeTransport()
        out = bridge.step(leader, t)
        self.assertIsNotNone(out)
        self.assertNotIn("unknown_joint", out)


class TestDeadband(unittest.TestCase):
    def test_every_step_sends_latest_position(self):
        """teleop_joints 直写模式：遥操作每帧都发当前绝对位置（不用死区抑制发送）。"""
        bridge = make_bridge(deadband=2.0, cmd_name="teleop_joints")
        leader = FakeLeader()
        t = FakeTransport()
        # 首次发
        bridge.step(leader, t)
        self.assertEqual(len(t.sent), 1)
        # 第二次：小变化 (0.1) 也应发送且反映最新位置（每帧无条件发）
        leader.action = full_action(shoulder_pan=0.1)
        out = bridge.step(leader, t)
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out["shoulder_pan"], 0.1, places=6)
        # 第三次：回到原位置也应发（持续跟踪，不回退）
        leader.action = full_action(shoulder_pan=0.0)
        bridge.step(leader, t)
        self.assertEqual(len(t.sent), 3)

    def test_move_joints_resend_after_periodic_timeout(self):
        """move_joints 插值模式：小变化先抑制，超兜底周期后仍无条件补发。"""
        bridge = make_bridge(deadband=2.0, cmd_name="move_joints")
        leader = FakeLeader()
        t = FakeTransport()
        bridge._last_send_t = time.monotonic() - 1.0
        bridge.step(leader, t)
        self.assertEqual(len(t.sent), 1)


class TestVelocityLimit(unittest.TestCase):
    def test_big_jump_limited_to_max_velocity(self):
        bridge = make_bridge(max_velocity=10.0)
        leader = FakeLeader()
        t = FakeTransport()
        bridge.step(leader, t)  # 初始 0
        # 大步跳到 90 -> 应被限制为上一帧 +10
        leader.action = full_action(shoulder_pan=90.0)
        out = bridge.step(leader, t)
        self.assertAlmostEqual(out["shoulder_pan"], 10.0, places=6)


class TestEStop(unittest.TestCase):
    def test_leader_failure_triggers_estop_and_sends_estop(self):
        bridge = make_bridge()
        leader = FakeLeader()
        t = FakeTransport()
        bridge.step(leader, t)  # 正常一帧
        leader.fail = True
        out = bridge.step(leader, t)
        self.assertIsNone(out)
        self.assertTrue(bridge.estop_active)
        # 应发过 estop
        self.assertTrue(any(s.get("cmd") == "estop" for s in t.sent))

    def test_empty_action_triggers_estop(self):
        bridge = make_bridge()
        leader = FakeLeader()
        leader.action = {}
        t = FakeTransport()
        out = bridge.step(leader, t)
        self.assertIsNone(out)
        self.assertTrue(bridge.estop_active)


class TestRunLoop(unittest.TestCase):
    def test_run_stops_on_estop_and_sends_final_estop(self):
        bridge = make_bridge(estop_tolerance_s=0.2, read_hz=50, send_hz=50)
        leader = FakeLeader()
        t = FakeTransport()
        # 让 get_action 抛异常 -> 触发急停 -> run 退出
        leader.fail = True
        import time
        bridge.run(leader, t, stop_event=None)
        self.assertTrue(bridge.estop_active)
        self.assertTrue(any(s.get("cmd") == "estop" for s in t.sent))


if __name__ == "__main__":
    unittest.main(verbosity=2)

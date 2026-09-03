"""三轮 Kiwi 全向底盘底层控制测试。"""
import math
import sys
import unittest
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(CODE_DIR))

import kiwi_drive


class FakeSerial:
    def __init__(self):
        self.packets = []

    def write(self, data):
        self.packets.append(data)

    def flush(self):
        return None


class KiwiKinematicsTest(unittest.TestCase):
    def test_stop_returns_zero_for_all_three_wheels(self):
        speeds = kiwi_drive.wheel_rpm(0.0, 0.0, 0.0)

        self.assertEqual(speeds, {7: 0.0, 8: 0.0, 9: 0.0})

    def test_rotation_commands_same_wheel_rpm(self):
        speeds = kiwi_drive.wheel_rpm(0.0, 0.0, 1.0)
        values = list(speeds.values())

        self.assertTrue(all(value > 0.0 for value in values))
        self.assertAlmostEqual(values[0], values[1], places=6)
        self.assertAlmostEqual(values[1], values[2], places=6)

    def test_forward_has_no_reconstructed_rotation(self):
        speeds = kiwi_drive.wheel_rpm(0.10, 0.0, 0.0)

        vx, vy, omega = kiwi_drive.reconstruct_body_speed(speeds)
        self.assertAlmostEqual(omega, 0.0, places=6)
        self.assertAlmostEqual(vx, 0.10, places=6)
        self.assertNotEqual(len({round(value, 6) for value in speeds.values()}), 1)

    def test_lateral_motion_has_no_reconstructed_rotation(self):
        speeds = kiwi_drive.wheel_rpm(0.0, 0.10, 0.0)

        vx, vy, omega = kiwi_drive.reconstruct_body_speed(speeds)
        self.assertAlmostEqual(omega, 0.0, places=6)
        self.assertAlmostEqual(vy, 0.10, places=6)
        self.assertNotEqual(len({round(value, 6) for value in speeds.values()}), 1)

    def test_move_writes_a_speed_packet_for_each_wheel(self):
        serial = FakeSerial()

        kiwi_drive.move(serial, 0.10, 0.0, 0.0)

        self.assertEqual(len(serial.packets), 3)
        self.assertEqual([packet[2] for packet in serial.packets], [7, 8, 9])

    def test_speed_is_limited_to_safe_raw_range(self):
        raw_speed = kiwi_drive.rpm_to_raw(10_000.0)

        self.assertEqual(raw_speed, kiwi_drive.MAX_RAW_SPEED)


if __name__ == "__main__":
    unittest.main(verbosity=2)

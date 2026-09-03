"""Tests for the wired camera car controller."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import camera_car_drive as car
from camera_car_gamepad import GamepadSnapshot, normalize_axis


class CameraCarConfigTest(unittest.TestCase):
    def test_default_rear_wheels_are_reversed(self) -> None:
        config = car.CarConfig()
        self.assertEqual(config.directions, {5: 1, 6: -1, 4: -1})

    def test_wheel_kinematics_uses_configured_ids(self) -> None:
        config = car.CarConfig()
        speeds = car.wheel_rpm(config, 0.05, 0.0, 0.0)

        self.assertEqual(set(speeds), {4, 5, 6})
        self.assertAlmostEqual(speeds[5], 0.0, places=6)
        self.assertGreater(speeds[6], 0.0)
        self.assertLess(speeds[4], 0.0)

    def test_stop_returns_zero_for_all_wheels(self) -> None:
        config = car.CarConfig()
        speeds = car.wheel_rpm(config, *car.motion_vector(car.Motion.STOP, config))

        self.assertEqual(set(speeds), {4, 5, 6})
        self.assertEqual(set(speeds.values()), {0.0})

    def test_rotation_commands_same_wheel_rpm(self) -> None:
        config = car.CarConfig()
        speeds = car.wheel_rpm(config, *car.motion_vector(car.Motion.ROTATE_LEFT, config))
        values = list(speeds.values())

        self.assertTrue(all(value > 0.0 for value in values))
        self.assertAlmostEqual(values[0], values[1], places=6)
        self.assertAlmostEqual(values[1], values[2], places=6)

    def test_rpm_is_limited_to_safe_raw_range(self) -> None:
        self.assertEqual(car.rpm_to_raw(10_000.0), car.MAX_RAW_SPEED)


class CameraCarSerialTest(unittest.TestCase):
    def test_forward_writes_one_speed_packet_per_wheel(self) -> None:
        serial = car.FakeSerial()
        config = car.CarConfig()

        car.command(serial, config, car.Motion.FORWARD)

        self.assertEqual(len(serial.packets), 3)
        self.assertEqual([packet[2] for packet in serial.packets], [5, 6, 4])

    def test_stop_writes_zero_to_all_wheels(self) -> None:
        serial = car.FakeSerial()
        config = car.CarConfig()

        car.stop(serial, config)

        self.assertEqual(len(serial.packets), 3)
        self.assertEqual([packet[2] for packet in serial.packets], [5, 6, 4])
        for packet in serial.packets:
            self.assertEqual(packet[6:8], b"\x00\x00")


class CameraCarGamepadTest(unittest.TestCase):
    def test_axis_normalization(self) -> None:
        self.assertEqual(normalize_axis(0), 0.0)
        self.assertAlmostEqual(normalize_axis(16_383), 0.5, places=4)
        self.assertEqual(normalize_axis(40_000), 1.0)

    def test_gamepad_moving_uses_deadzone(self) -> None:
        idle = GamepadSnapshot(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
        active = GamepadSnapshot(0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0)

        self.assertFalse(idle.moving)
        self.assertTrue(active.moving)

    def test_analog_move_writes_three_packets(self) -> None:
        serial = car.FakeSerial()
        config = car.CarConfig()

        car.move(serial, config, 0.03, 0.0, 0.0)

        self.assertEqual(len(serial.packets), 3)
        self.assertEqual([packet[2] for packet in serial.packets], [5, 6, 4])


if __name__ == "__main__":
    unittest.main(verbosity=2)

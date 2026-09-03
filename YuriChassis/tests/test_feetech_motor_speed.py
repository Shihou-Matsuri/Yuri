"""STS3215 电机速度编码测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import feetech


class MotorSpeedEncodingTest(unittest.TestCase):
    def test_positive_speed_keeps_direction_bit_clear(self):
        self.assertEqual(feetech.encode_motor_speed(639), 0x027F)

    def test_negative_speed_uses_direction_bit_with_same_magnitude(self):
        self.assertEqual(feetech.encode_motor_speed(-639), 0x827F)

    def test_opposite_directions_have_equal_magnitude_bits(self):
        forward = feetech.encode_motor_speed(1279)
        reverse = feetech.encode_motor_speed(-1279)

        self.assertEqual(forward & 0x7FFF, reverse & 0x7FFF)
        self.assertEqual(reverse & 0x8000, 0x8000)

    def test_rejects_speed_above_direction_bit_capacity(self):
        with self.assertRaises(ValueError):
            feetech.encode_motor_speed(0x8000)


if __name__ == "__main__":
    unittest.main(verbosity=2)

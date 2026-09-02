import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.perception import (  # noqa: E402
    Homography,
    PerceptionUnavailable,
    detections_to_blocks,
    verify_pick,
)
from yuriarm.planner import Block  # noqa: E402


class TestHomography(unittest.TestCase):
    def test_identity_homography(self):
        h = Homography([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        x, y = h.pixel_to_mm(123.0, 456.0)
        self.assertAlmostEqual(x, 123.0, places=6)
        self.assertAlmostEqual(y, 456.0, places=6)

    def test_scaled_homography(self):
        # 每像素 = 0.1mm：像素 (100, 200) -> mm (10, 20)
        h = Homography([[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]])
        x, y = h.pixel_to_mm(100.0, 200.0)
        self.assertAlmostEqual(x, 10.0, places=6)
        self.assertAlmostEqual(y, 20.0, places=6)

    def test_load_missing_raises(self):
        with self.assertRaises(PerceptionUnavailable):
            Homography.load(Path(".") / "does_not_exist.json")


class TestDetectionsToBlocks(unittest.TestCase):
    def test_convert(self):
        h = Homography([[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]])
        dets = [{"label": "red", "confidence": 0.9, "bbox": [0, 0, 100, 100]}]
        blocks = detections_to_blocks(dets, h, cube_size_mm=30.0)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].color, "red")
        # 中心 (50,50) 像素 -> (5,5) mm
        self.assertAlmostEqual(blocks[0].x_mm, 5.0, places=6)
        self.assertAlmostEqual(blocks[0].y_mm, 5.0, places=6)
        self.assertEqual(blocks[0].z_mm, 30.0)


class TestVerifyPick(unittest.TestCase):
    def test_ok_when_target_removed_others_stay(self):
        initial = [Block(x_mm=0, y_mm=0, color="red"), Block(x_mm=100, y_mm=100, color="blue")]
        current = [Block(x_mm=100, y_mm=100, color="blue")]
        v = verify_pick(initial, current, Block(x_mm=0, y_mm=0, color="red"))
        self.assertTrue(v["ok"])
        self.assertTrue(v["target_removed"])
        self.assertEqual(v["others_moved"], [])

    def test_fail_when_target_remains(self):
        initial = [Block(x_mm=0, y_mm=0, color="red")]
        current = [Block(x_mm=0, y_mm=0, color="red")]
        v = verify_pick(initial, current, Block(x_mm=0, y_mm=0, color="red"))
        self.assertFalse(v["ok"])
        self.assertFalse(v["target_removed"])

    def test_fail_when_other_moved(self):
        initial = [Block(x_mm=0, y_mm=0, color="red"), Block(x_mm=100, y_mm=100, color="blue")]
        current = [Block(x_mm=100, y_mm=150, color="blue")]
        v = verify_pick(initial, current, Block(x_mm=0, y_mm=0, color="red"))
        self.assertFalse(v["ok"])
        self.assertEqual(len(v["others_moved"]), 1)


if __name__ == "__main__":
    unittest.main()

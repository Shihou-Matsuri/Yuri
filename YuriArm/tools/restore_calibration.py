"""从电机 EEPROM 恢复标定文件。

场景：机械臂之前标定过（标定值已写入电机 EEPROM），但标定 JSON 文件丢失/换机。
本工具读取 Homing_Offset / Min_Position_Limit / Max_Position_Limit 并写回
lerobot 标定文件（~/.cache/huggingface/lerobot/calibration/robots/so101_follower/{id}.json），
无需重新交互式标定。纯读取 + 写文件，不产生任何运动。

用法:
    python tools/restore_calibration.py --port COM14 --id zgq_follower_arm
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lerobot.robots.so101_follower import SO101Follower  # noqa: E402
from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从电机 EEPROM 恢复标定文件")
    ap.add_argument("--port", required=True)
    ap.add_argument("--id", default="zgq_follower_arm")
    args = ap.parse_args(argv)

    robot = SO101Follower(SO101FollowerConfig(port=args.port, id=args.id))
    try:
        robot.bus.connect()
        cal = robot.bus.read_calibration()
        robot.calibration = cal
        robot._save_calibration()  # noqa: SLF001  (与 lerobot 内部流程一致)
    finally:
        try:
            robot.bus.disconnect()
        except Exception:
            pass

    print(f"[OK] 标定已从 EEPROM 恢复 -> {robot.calibration_fpath}")
    for name, c in cal.items():
        print(f"  {name:14s} id={c.id} homing={c.homing_offset} range=[{c.range_min},{c.range_max}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())

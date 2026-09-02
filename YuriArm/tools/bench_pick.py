"""M0 冒烟测试：台上单臂夹取（有线先行，设计文档 §6 M0）。

流程：连接 → home → pick_high → pick_low → 合拢(负载判夹) → 提起 → drop → 张开。
真机模式需要：标定文件存在 + 已 teach pick_high/pick_low/drop 三个姿态。
--mock 模式用仿真后端（夹爪间模拟有方块），无需硬件即可验证整条链路。

用法:
    python tools/bench_pick.py --mock
    python tools/bench_pick.py            # 真机（lerobot 环境，COM7）
    python tools/bench_pick.py --config path/to/arm.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.arm import YuriArm  # noqa: E402
from yuriarm.config import load_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="M0 台上单臂夹取冒烟测试")
    ap.add_argument("--config", default=None)
    ap.add_argument("--mock", action="store_true", help="使用仿真后端")
    args = ap.parse_args(argv)

    cfg = load_config(args.config or None)
    arm = YuriArm(cfg, mock=args.mock)
    steps: list[tuple[str, bool, str]] = []

    def check(name: str, fn):
        try:
            result = fn()
            if isinstance(result, dict) and result.get("ok") is False:
                reason = result.get("reason") or "操作失败（返回 ok=false）"
                steps.append((name, False, reason))
                print(f"[FAIL] {name}: {reason}")
                return
            steps.append((name, True, ""))
            print(f"[PASS] {name}: {result}")
        except Exception as e:  # noqa: BLE001
            steps.append((name, False, f"{type(e).__name__}: {e}"))
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")

    print(f"== bench_pick 开始（backend={arm.backend.name}）==")
    check("connect", arm.connect)
    if args.mock:
        # 模拟夹爪间有方块：验证负载判定路径
        arm.backend.set_block(True)

    # 校验姿态是否已示教（pick_high/pick_low/drop）
    missing = [n for n in (cfg.pick["pick_high_pose"], cfg.pick["pick_low_pose"], cfg.pick["drop_pose"])
               if not cfg.poses.get(n)]
    if missing:
        print(f"[SKIP] 缺少已示教姿态 {missing}，跳过拾取周期（先运行: python -m yuriarm --mock teach <pose> 或用真机 teach）")
        steps.append(("pick", False, f"缺少姿态 {missing}"))
    else:
        home = cfg.poses.get("home")
        if home and any(home.values()):
            check("home", arm.home)
        check("pick", arm.pick)
    if args.mock:
        arm.backend.set_block(False)
    check("disconnect", arm.disconnect)

    failed = [s for s in steps if not s[1]]
    print(f"== 结果: {len(steps) - len(failed)}/{len(steps)} 通过 ==")
    if failed:
        print("失败步骤:", [s[0] for s in failed])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

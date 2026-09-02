"""根据 configs/default.json 的颜色范围生成合成示例图（与当前标定保持一致）。

用法:
  python tools/make_sample.py [--config configs/default.json] [--out examples/sample_cubes.png]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402

# 每个颜色在示例图中的方块位置（同尺寸 90px）
LAYOUT = [
    ("red", [(60, 100), (180, 250)]),
    ("green", [(260, 100)]),
    ("blue", [(400, 90), (520, 230)]),
    ("orange", [(90, 330)]),
    ("purple", [(330, 300), (500, 380)]),
    ("yellow", [(550, 300)]),
]


def hsv_mid_bgr(ranges: list) -> tuple[int, int, int]:
    """取第一个 HSV 范围的中点并转 BGR（红/橙等回绕由范围本身决定）。"""
    if not ranges:
        return (200, 200, 200)
    lo, hi = ranges[0]
    h = (int(lo[0]) + int(hi[0])) // 2
    s = (int(lo[1]) + int(hi[1])) // 2
    v = (int(lo[2]) + int(hi[2])) // 2
    bgr = cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return (int(bgr[0]), int(bgr[1]), int(bgr[2]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--out", default="examples/sample_cubes.png")
    args = ap.parse_args()

    colors = load_config(args.config).get("colors", {})
    if not colors:
        print("配置缺少 colors", file=sys.stderr)
        sys.exit(1)

    img = np.full((480, 640, 3), 200, np.uint8)
    img[380:, :] = 215  # 浅色桌面
    for label, poses in LAYOUT:
        if label not in colors:
            continue
        bgr = hsv_mid_bgr(colors[label].get("hsv_ranges") or [])
        for (x, y) in poses:
            cv2.rectangle(img, (x, y), (x + 90, y + 90), bgr, -1)
            cv2.rectangle(img, (x, y), (x + 90, y + 22), tuple(min(c + 45, 255) for c in bgr), -1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), img):
        print(f"写入失败: {out}", file=sys.stderr)
        sys.exit(1)
    print(f"已生成 {out}（{img.shape[1]}x{img.shape[0]}），颜色来源: {list(colors.keys())}")


if __name__ == "__main__":
    main()

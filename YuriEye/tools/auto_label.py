"""对已有图片批量自动标注（经典 CV 检测器），输出 JSON sidecar（与 capture_dataset 相同格式）。

用法:
  python tools/auto_label.py --src data/raw [--config configs/default.json] [--no-relax-sv]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from yurieye.detector import CubeDetector  # noqa: E402

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/raw")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--no-relax-sv", action="store_true",
                    help="不放宽 S/V（默认放宽到 S>=50/V>=40，对曝光变化更鲁棒）")
    args = ap.parse_args()

    cfg = load_config(args.config)
    colors = cfg.get("colors", {})
    if not colors:
        print("配置缺少 colors", file=sys.stderr)
        sys.exit(1)

    if not args.no_relax_sv:
        # 放宽 V 下限以覆盖曝光变化；S 下限按颜色设置，
        # 暖色（红/橙/黄/蓝）要求高饱和以排除肤色（肤色 S 通常 <130），
        # 绿/紫本身饱和度较低，用更低阈值。
        s_floor = {
            "red": 130, "orange": 130, "yellow": 130,
            "green": 70, "blue": 130, "purple": 60,
        }
        colors = {
            label: {"hsv_ranges": [
                [[lo[0], s_floor.get(label, 80), 50], [hi[0], 255, 255]] for lo, hi in spec.get("hsv_ranges") or []
            ]}
            for label, spec in colors.items()
        }

    geometry = dict(cfg.get("cube", {}))
    src = Path(args.src)
    imgs = sorted(p for p in src.iterdir() if p.suffix.lower() in IMG_EXTS)
    if not imgs:
        print(f"没有图片: {src}", file=sys.stderr)
        sys.exit(1)
    # 分辨率自适应最小面积 + 顶部条带过滤：
    # - 小面积剔除键盘按键/高光等噪点（阈值 0.15% 图像面积）；
    # - 顶部条带（y 中心 < 6% 高度）剔除顶部黄色灯带等系统性误检。
    first = cv2.imread(str(imgs[0]))
    top_strip = 0.06
    if first is not None:
        H, W = first.shape[:2]
        geometry["min_area_px"] = max(float(geometry.get("min_area_px", 400)), 0.0015 * W * H)

    detector = CubeDetector(colors, geometry)

    def keep(det) -> bool:
        x, y, w, h = det["bbox"]
        if (y + h / 2) < top_strip * first.shape[0]:
            return False
        return True

    from collections import Counter
    total = Counter()
    n_empty = 0
    for p in imgs:
        img = cv2.imread(str(p))
        if img is None:
            print(f"跳过无法读取: {p.name}", file=sys.stderr)
            continue
        dets = [d for d in detector.detect(img) if keep(d.to_dict())]
        side = p.with_suffix(".json")
        side.write_text(json.dumps([d.to_dict() for d in dets], ensure_ascii=False, indent=2), encoding="utf-8")
        total.update(d.label for d in dets)
        if not dets:
            n_empty += 1
    print(f"标注完成: {len(imgs)} 张，空标注 {n_empty} 张")
    print("各类检出:", dict(total))


if __name__ == "__main__":
    main()

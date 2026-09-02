"""生成合成彩色立方体数据集（YOLO 格式），用于 ML 路径启动训练。

用法:
  python ml/make_synthetic_dataset.py --count 200 --out data/yolo --val-ratio 0.1

每张图：简单浅色背景 + 1~8 个随机位置/大小/旋转的彩色立方体（颜色取配置中值，
带亮度抖动），自动生成 YOLO 标注（轴对齐包围框）。训练前可与真实数据合并。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402


def hsv_mid_bgr(ranges: list) -> tuple[int, int, int]:
    if not ranges:
        return (180, 180, 180)
    lo, hi = ranges[0]
    h = (int(lo[0]) + int(hi[0])) // 2
    s = (int(lo[1]) + int(hi[1])) // 2
    v = (int(lo[2]) + int(hi[2])) // 2
    bgr = cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return (int(bgr[0]), int(bgr[1]), int(bgr[2]))


def rotate_points(points: np.ndarray, angle_deg: float, center) -> np.ndarray:
    """把以中心为原点的局部坐标点旋转 angle 度并平移到 center。"""
    rad = np.deg2rad(angle_deg)
    ca, sa = np.cos(rad), np.sin(rad)
    rot = np.array([[ca, -sa], [sa, ca]])
    return points @ rot.T + np.asarray(center, dtype=np.float32)


def cube_points(center, size: float, angle: float) -> np.ndarray:
    """返回旋转后正方形四角的整数坐标（用于先算框、后绘制）。"""
    half = size / 2
    corners = np.array([[-half, -half], [half, -half], [half, half], [-half, half]], dtype=np.float32)
    return rotate_points(corners, angle, center).astype(np.int32)


def render_cube(img: np.ndarray, bgr: tuple, pts: np.ndarray) -> None:
    """按已算好的四角绘制实心立方体（含顶面高光），返回轴对齐 bbox。"""
    cv2.fillPoly(img, [pts], bgr)
    top = np.array([
        pts[0],
        pts[1],
        pts[1] + ((pts[3] - pts[0]) * 0.25).astype(np.int32),
        pts[0] + ((pts[2] - pts[1]) * 0.25).astype(np.int32),
    ], dtype=np.int32)
    cv2.fillPoly(img, [top], tuple(min(c + 40, 255) for c in bgr))


def bbox_of(pts: np.ndarray) -> tuple[int, int, int, int]:
    x0, y0 = int(pts[:, 0].min()), int(pts[:, 1].min())
    x1, y1 = int(pts[:, 0].max()), int(pts[:, 1].max())
    return x0, y0, x1 - x0, y1 - y0


def place_cubes(img: np.ndarray, colors_bgr: list, max_try: int = 80) -> list[tuple[int, int, int, int, int]]:
    """随机放置立方体，避免与已有立方体重叠且完整落在画布内。"""
    H, W = img.shape[:2]
    boxes: list[tuple[int, int, int, int]] = []
    labels: list[tuple[int, int, int, int, int]] = []
    n_cubes = np.random.randint(1, 9)
    for _ in range(n_cubes):
        cls = np.random.randint(len(colors_bgr))
        size = float(np.random.uniform(50, 110))
        angle = float(np.random.uniform(-35, 35))
        placed = False
        for _try in range(max_try):
            cx = np.random.uniform(size, W - size)
            cy = np.random.uniform(size, H - size)
            pts = cube_points((cx, cy), size, angle)
            x, y, bw, bh = bbox_of(pts)
            if x < 0 or y < 0 or x + bw > W or y + bh > H:
                continue  # 越界，重试
            bb = (x, y, bw, bh)
            if all(not (bb[0] < b[0] + b[2] + 8 and bb[0] + bb[2] + 8 > b[0]
                        and bb[1] < b[1] + b[3] + 8 and bb[1] + bb[3] + 8 > b[1]) for b in boxes):
                # 先确认位置合法，再绘制（避免画了却不记标注导致数量对不上）
                render_cube(img, colors_bgr[cls], pts)
                boxes.append(bb)
                labels.append((cls, x, y, bw, bh))
                placed = True
                break
        if not placed:
            continue
    return labels


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--out", default="data/yolo")
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = load_config(args.config)
    colors = list(cfg.get("colors", {}).keys())
    if not colors:
        print("配置缺少 colors", file=sys.stderr)
        sys.exit(1)
    colors_bgr = [hsv_mid_bgr(cfg["colors"][c].get("hsv_ranges") or []) for c in colors]

    out = Path(args.out)
    for sub in ("images", "labels"):
        p = out / sub
        if p.is_dir():
            shutil.rmtree(p)
    (out / "images" / "train").mkdir(parents=True, exist_ok=True)
    (out / "images" / "val").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "val").mkdir(parents=True, exist_ok=True)

    np.random.seed(args.seed)
    n_val = max(1, int(args.count * args.val_ratio))
    n_train = args.count - n_val
    counts = {"train": 0, "val": 0}
    for i in range(args.count):
        split = "val" if i >= n_train else "train"
        img = np.full((640, 640, 3), 205, np.uint8)
        img += np.random.randint(-8, 8, img.shape, dtype=np.int16).clip(0, 255).astype(np.uint8)
        labels = place_cubes(img, colors_bgr)
        if not labels:
            continue
        name = f"synth_{i:05d}"
        cv2.imwrite(str(out / "images" / split / (name + ".jpg")), img)
        lines = []
        for cls, x, y, bw, bh in labels:
            cx = (x + bw / 2) / 640
            cy = (y + bh / 2) / 640
            lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw/640:.6f} {bh/640:.6f}")
        (out / "labels" / split / (name + ".txt")).write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts[split] += 1

    yaml = (
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n" + "".join(f"  {i}: {c}\n" for i, c in enumerate(colors))
    )
    (out / "data.yaml").write_text(yaml, encoding="utf-8")
    print(f"合成数据集生成完成: train={counts['train']} val={counts['val']} 类别={colors}")
    print(f"配置: {out / 'data.yaml'}")


if __name__ == "__main__":
    main()

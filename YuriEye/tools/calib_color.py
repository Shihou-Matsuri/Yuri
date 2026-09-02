"""颜色标定工具：点击画面采样 HSV 范围并保存到配置。

用法:
  python tools/calib_color.py                      # 实时相机
  python tools/calib_color.py --image xx.png       # 对静态图标定
  python tools/calib_color.py --config configs/default.json

操作:
  鼠标左键  在目标颜色上点击，采样周围 patch 的 HSV 并累计
  按键 0~9  切换当前标定颜色（对应配置 colors 的键顺序）
  按键 s    把采样结果合并写入配置文件
  按键 q/ESC 退出（不保存）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.camera import Camera  # noqa: E402
from yurieye.color_utils import merge_samples, sample_patch_hsv  # noqa: E402
from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402


class ColorCalibrator:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.cfg = load_config(self.config_path)
        self.colors = self.cfg.setdefault("colors", {})
        self.labels = list(self.colors.keys())
        self.current = 0
        self.samples: dict[str, list[dict]] = {label: [] for label in self.labels}
        self.frame = None
        self.mouse_pt = None

    def on_mouse(self, event, x, y, _flags, _param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and self.frame is not None:
            sample = sample_patch_hsv(self.frame, (x, y))
            if sample is not None:
                label = self.labels[self.current]
                self.samples[label].append(sample)
                print(f"[{label}] 采样 {len(self.samples[label])} 次: ranges={sample.get('ranges')}")

    def render(self):
        out = self.frame.copy()
        label = self.labels[self.current]
        text = f"标定: {label} (按键 0-9 切换) | 左键采样 | s=保存 | q=退出"
        cv2.putText(out, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        # 叠加当前颜色已采样范围对应的掩码，直观预览
        merged = merge_samples(self.samples[label])
        if merged:
            hsv = cv2.cvtColor(self.frame, cv2.COLOR_BGR2HSV)
            from yurieye.color_utils import hsv_mask
            mask = hsv_mask(hsv, merged)
            out[mask > 0] = (0, 0, 255)
        return out

    def save(self) -> None:
        for label, samples in self.samples.items():
            ranges = merge_samples(samples)
            if ranges:
                self.colors[label]["hsv_ranges"] = ranges
                print(f"[{label}] 写入 hsv_ranges = {ranges}")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        print(f"已保存到 {self.config_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--image", default=None)
    ap.add_argument("--camera-index", type=int, default=None)
    args = ap.parse_args()

    cal = ColorCalibrator(args.config)
    if not cal.labels:
        print("配置中没有 colors 键", file=sys.stderr)
        sys.exit(1)

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"无法读取图片: {args.image}", file=sys.stderr)
            sys.exit(1)
    else:
        cam = Camera(index=args.camera_index if args.camera_index is not None
                     else cal.cfg.get("camera", {}).get("index", 1))
        ok, frame = cam.read()
        if not ok:
            print("读取摄像头失败", file=sys.stderr)
            cam.release()
            sys.exit(1)
        cam.release()

    cal.frame = frame
    cv2.namedWindow("YuriEye 颜色标定")
    cv2.setMouseCallback("YuriEye 颜色标定", cal.on_mouse)

    while True:
        cv2.imshow("YuriEye 颜色标定", cal.render())
        key = cv2.waitKey(20) & 0xFF
        if key == ord("s"):
            cal.save()
        elif key == ord("q") or key == 27:
            break
        elif ord("0") <= key <= ord("9"):
            idx = key - ord("0")
            if idx < len(cal.labels):
                cal.current = idx
                print(f"切换标定颜色: {cal.labels[idx]}")
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

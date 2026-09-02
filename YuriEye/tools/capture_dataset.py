"""采集数据集：从摄像头拍摄 N 帧，保存原图与（可选）基线检测标注 JSON。

用法:
  python tools/capture_dataset.py --count 100 --interval 0.2 --out data/raw --annotate
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.camera import Camera  # noqa: E402
from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from yurieye.detector import CubeDetector  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--interval", type=float, default=0.2)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--camera-index", type=int, default=None)
    ap.add_argument("--annotate", action="store_true", help="同时用基线检测器生成 JSON 标注")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    camera_cfg = cfg.get("camera", {})
    colors_cfg = cfg.get("colors", {})
    detector = CubeDetector(colors_cfg, cfg.get("cube", {})) if args.annotate else None

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    index = args.camera_index if args.camera_index is not None else camera_cfg.get("index", 1)
    cam = Camera(index=index, width=camera_cfg.get("width", 1280), height=camera_cfg.get("height", 720))
    print("相机信息:", cam.info())
    try:
        for i in range(args.count):
            ok, frame = cam.read()
            if not ok:
                print("读取帧失败，中止", file=sys.stderr)
                break
            base = out_dir / f"{stamp}_{i:04d}"
            cv2.imwrite(str(base.with_suffix(".jpg")), frame)
            if detector is not None:
                dets = detector.detect(frame)
                with open(str(base.with_suffix(".json")), "w", encoding="utf-8") as f:
                    json.dump([d.to_dict() for d in dets], f, ensure_ascii=False, indent=2)
            if not args.no_show:
                cv2.imshow("capture", frame)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
            if args.interval > 0:
                time.sleep(args.interval)
        print(f"已采集 {i + 1} 帧 -> {out_dir}")
    finally:
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

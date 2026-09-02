"""YOLO 推理工具：摄像头或图片实时检测彩色立方体。

用法:
  python tools/detect_ml.py                          # 实时（默认权重 ml/weights/best.pt）
  python tools/detect_ml.py --image xx.jpg --json    # 单图，输出 JSON
  python tools/detect_ml.py --weights path/to/best.pt --conf 0.3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_WEIGHTS = Path(__file__).resolve().parents[1] / "ml" / "weights" / "best.pt"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(DEFAULT_WEIGHTS))
    ap.add_argument("--image", default=None)
    ap.add_argument("--camera-index", type=int, default=1)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-show", action="store_true")
    ap.add_argument("--max-frames", type=int, default=0)
    args = ap.parse_args()

    weights = Path(args.weights)
    if not weights.exists():
        print(f"权重不存在: {weights}（先训练，见 ml/README.md）", file=sys.stderr)
        sys.exit(1)

    try:
        from ultralytics import YOLO
    except ImportError as e:
        print("需要 yurieye GPU 环境（ultralytics），见 scripts/setup_env.md", file=sys.stderr)
        raise SystemExit(1) from e

    model = YOLO(str(weights))
    names = model.names

    def run(frame):
        res = model.predict(frame, conf=args.conf, imgsz=args.imgsz, device=0 if __import__("torch").cuda.is_available() else "cpu", verbose=False)[0]
        dets = [{
            "label": names[int(b.cls)],
            "confidence": round(float(b.conf), 3),
            "bbox": [int(v) for v in b.xyxy[0]],
        } for b in res.boxes]
        if args.json:
            print(json.dumps(dets, ensure_ascii=False))
        annotated = res.plot()
        return dets, annotated

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"无法读取图片: {args.image}", file=sys.stderr)
            sys.exit(1)
        dets, annotated = run(frame)
        if not args.no_show:
            cv2.imshow("YuriEye-ML", annotated)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        print(f"检测到 {len(dets)} 个立方体")
        return

    from yurieye.camera import Camera
    cam = Camera(index=args.camera_index, width=1280, height=720, fps=30)
    print("相机信息:", cam.info())
    frame_count = 0
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                break
            dets, annotated = run(frame)
            if not args.no_show:
                cv2.imshow("YuriEye-ML", annotated)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
            frame_count += 1
            if args.max_frames and frame_count >= args.max_frames:
                break
    finally:
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

"""实时检测演示：摄像头或单张图片。

用法:
  python tools/live_detect.py                   # 实时（使用 configs/default.json 的 camera.index）
  python tools/live_detect.py --image xx.png    # 单张图片离线测试
  python tools/live_detect.py --debug           # 叠加颜色掩码调试视图
  python tools/live_detect.py --json            # 每帧输出 JSON 结果
  python tools/live_detect.py --no-show         # 不弹窗口（适合脚本/远程）
  python tools/live_detect.py --max-frames 10   # 处理 N 帧后退出
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.camera import Camera  # noqa: E402
from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from yurieye.detector import CubeDetector  # noqa: E402
from yurieye.visualize import draw_detections, overlay_masks  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--camera-index", type=int, default=None)
    ap.add_argument("--image", default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-show", action="store_true")
    ap.add_argument("--max-frames", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config(args.config)
    camera_cfg = cfg.get("camera", {})
    cube_cfg = cfg.get("cube", {})
    colors_cfg = cfg.get("colors", {})

    if not colors_cfg:
        print("配置中缺少 colors，请检查 configs/default.json", file=sys.stderr)
        sys.exit(1)

    detector = CubeDetector(colors_cfg, cube_cfg)

    def handle_frame(frame, count: int) -> None:
        dets = detector.detect(frame)
        if args.json:
            print(json.dumps([d.to_dict() for d in dets], ensure_ascii=False))
        out = draw_detections(frame, dets, colors_cfg)
        if args.debug:
            out = overlay_masks(out, colors_cfg)
        if not args.no_show:
            cv2.imshow("YuriEye", out)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                raise KeyboardInterrupt

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"无法读取图片: {args.image}", file=sys.stderr)
            sys.exit(1)
        dets = detector.detect(frame)
        if args.json:
            print(json.dumps([d.to_dict() for d in dets], ensure_ascii=False, indent=2))
        print(f"检测到 {len(dets)} 个立方体")
        out = draw_detections(frame, dets, colors_cfg)
        if args.debug:
            out = overlay_masks(out, colors_cfg)
        if not args.no_show:
            cv2.imshow("YuriEye", out)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return

    index = args.camera_index if args.camera_index is not None else camera_cfg.get("index", 1)
    cam = Camera(
        index=index,
        width=camera_cfg.get("width", 1280),
        height=camera_cfg.get("height", 720),
        fps=camera_cfg.get("fps", 30),
        auto_exposure=camera_cfg.get("auto_exposure", True),
        exposure=camera_cfg.get("exposure", -5.0),
        auto_white_balance=camera_cfg.get("auto_white_balance", True),
    )
    print("相机信息:", cam.info())
    frame_count = 0
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                print("读取帧失败", file=sys.stderr)
                break
            handle_frame(frame, frame_count)
            frame_count += 1
            if args.max_frames and frame_count >= args.max_frames:
                break
    except KeyboardInterrupt:
        pass
    finally:
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

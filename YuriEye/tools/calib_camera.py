"""相机内参标定：从摄像头或图片目录收集棋盘格视图并标定内参。

用法:
  python tools/calib_camera.py --source camera            # 按空格键采集含棋盘格的画面，采集>=8张后按 c 标定
  python tools/calib_camera.py --source images/chess      # 扫描目录下所有棋盘格图片
  python tools/calib_camera.py --pattern 9 6 --square 25  # 棋盘格内角点数与格宽(mm)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.calib import calibrate_from_images, find_chessboard_corners  # noqa: E402
from yurieye.camera import Camera  # noqa: E402
from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["camera", "images"], default="camera")
    ap.add_argument("--dir", default="data/chessboard")
    ap.add_argument("--pattern", nargs=2, type=int, default=[9, 6])
    ap.add_argument("--square", type=float, default=25.0)
    ap.add_argument("--min-views", type=int, default=8)
    ap.add_argument("--out", default="configs/camera_calibration.json")
    ap.add_argument("--camera-index", type=int, default=None)
    args = ap.parse_args()
    pattern = tuple(args.pattern)

    if args.source == "images":
        img_dir = Path(args.dir)
        images = [cv2.imread(str(p)) for p in sorted(img_dir.glob("*")) if p.suffix.lower() in (".jpg", ".png", ".bmp")]
        images = [img for img in images if img is not None]
        if not images:
            print(f"目录中没有图片: {img_dir}", file=sys.stderr)
            sys.exit(1)
        cal = calibrate_from_images(images, pattern, args.square)
        cal.save(args.out)
        print(f"RMS={cal.rms:.4f}, K={cal.k.tolist()}, 已保存 {args.out}")
        return

    # 摄像头交互模式
    cfg = load_config()
    cam = Camera(index=args.camera_index if args.camera_index is not None
                 else cfg.get("camera", {}).get("index", 1))
    collected: list = []
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                print("读取帧失败", file=sys.stderr)
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners = find_chessboard_corners(gray, pattern)
            disp = frame.copy()
            if corners is not None:
                cv2.drawChessboardCorners(disp, pattern, corners, True)
            cv2.putText(disp, f"已采集 {len(collected)}/{args.min_views} | 空格=采集 c=标定 q=退出",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow("chessboard", disp)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(" ") and corners is not None:
                collected.append(frame.copy())
                print(f"采集第 {len(collected)} 张")
            elif key == ord("c") and len(collected) >= 3:
                break
            elif key in (27, ord("q")):
                return
        if len(collected) < 3:
            print("有效视图不足，未标定", file=sys.stderr)
            return
        cal = calibrate_from_images(collected, pattern, args.square)
        cal.save(args.out)
        print(f"RMS={cal.rms:.4f}, 视图数={len(collected)}, 已保存 {args.out}")
    finally:
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

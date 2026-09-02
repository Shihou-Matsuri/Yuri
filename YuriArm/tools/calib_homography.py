"""俯视相机 → 桌面 mm 的单应标定（设计文档 §3.2 第 2 步）。

两种输入：
1. 棋盘格：--chessboard --images-dir DIR --pattern 9 6 --square-mm 25
   （检测每个角点，把像素点映射到 mm 网格，cv2.findHomography）
2. 手工点对：--from-points points.json
   （[{"pixel": [x,y], "mm": [x,y]}, ...]，适合没有棋盘格时用 ArUco/直尺量）

输出 JSON（默认 YuriArm/configs/homography.json）：
    {"H": [[...]], "image_size": [w,h], "reproj_error": mm, "points": n}

用法:
    python tools/calib_homography.py --chessboard --images-dir ./chess_imgs --pattern 9 6 --square-mm 25
    python tools/calib_homography.py --from-points ./points.json
    python tools/calib_homography.py --chessboard --camera --count 8   # 从摄像头采集
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402


def detect_chessboard_corners(gray: np.ndarray, pattern: tuple[int, int]):
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_FAST_CHECK
    found, corners = cv2.findChessboardCorners(gray, pattern, flags)
    if not found:
        return None
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)


def corners_to_mm_grid(pattern: tuple[int, int], square_mm: float) -> np.ndarray:
    cols, rows = pattern
    obj = np.zeros((cols * rows, 2), np.float32)
    obj[:, 0] = np.repeat(np.arange(cols), rows)
    obj[:, 1] = np.tile(np.arange(rows), cols)
    return obj * square_mm


def compute_homography(src_pts: np.ndarray, dst_pts: np.ndarray) -> tuple[np.ndarray, float]:
    """src=像素, dst=mm。返回 (H, 重投影误差 mm)。"""
    if src_pts.shape[0] < 4:
        raise ValueError(f"至少需要 4 个点对，当前 {src_pts.shape[0]}")
    h, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if h is None:
        raise ValueError("findHomography 失败（点对可能共线/共面异常）")
    projected = cv2.perspectiveTransform(src_pts.reshape(-1, 1, 2), h).reshape(-1, 2)
    err = float(np.mean(np.linalg.norm(projected - dst_pts, axis=1)))
    return h, err


def save_homography(path: Path, h: np.ndarray, reproj_error: float,
                    image_size: tuple[int, int] | None, method: str, n_points: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "H": h.tolist(),
        "image_size": list(image_size) if image_size else None,
        "reproj_error": round(reproj_error, 4),
        "method": method,
        "points": n_points,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存单应 -> {path}（reproj_error={reproj_error:.3f}mm，{n_points} 个点）")


def from_chessboard(images: list[np.ndarray], pattern: tuple[int, int],
                    square_mm: float) -> tuple[np.ndarray, float, tuple[int, int]]:
    mm_grid = corners_to_mm_grid(pattern, square_mm)
    src_pts, dst_pts = [], []
    image_size = None
    for img in images:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = detect_chessboard_corners(gray, pattern)
        if corners is None:
            continue
        src_pts.append(corners.reshape(-1, 2))
        dst_pts.append(mm_grid)
        image_size = (gray.shape[1], gray.shape[0])
    if not src_pts:
        raise ValueError("所有图像都未检测到棋盘格")
    h, err = compute_homography(np.vstack(src_pts), np.vstack(dst_pts))
    return h, err, image_size  # type: ignore[return-value]


def from_points(pairs: list[dict]) -> tuple[np.ndarray, float, None]:
    src = np.asarray([[p["pixel"][0], p["pixel"][1]] for p in pairs], dtype=np.float32)
    dst = np.asarray([[p["mm"][0], p["mm"][1]] for p in pairs], dtype=np.float32)
    h, err = compute_homography(src, dst)
    return h, err, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="俯视→桌面单应标定")
    ap.add_argument("--chessboard", action="store_true")
    ap.add_argument("--images-dir", default=None)
    ap.add_argument("--camera", action="store_true", help="从摄像头逐张采集（配合 --chessboard）")
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--pattern", nargs=2, type=int, default=[9, 6])
    ap.add_argument("--square-mm", type=float, default=25.0)
    ap.add_argument("--from-points", default=None, help="点对 JSON 文件")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "configs" / "homography.json"))
    args = ap.parse_args(argv)

    out = Path(args.out)
    pattern = tuple(args.pattern)

    try:
        if args.from_points:
            with open(args.from_points, "r", encoding="utf-8") as f:
                pairs = json.load(f)
            h, err, size = from_points(pairs)
            save_homography(out, h, err, size, "points", len(pairs))
            return 0

        if args.camera:
            images = []
            cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
            if not cap.isOpened():
                print("无法打开摄像头", file=sys.stderr)
                return 1
            print(f"请把棋盘格放在桌面视野内，按 SPACE 采集（共 {args.count} 张，ESC 取消）")
            while len(images) < args.count:
                ok, frame = cap.read()
                if not ok:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                found = detect_chessboard_corners(gray, pattern) is not None
                hint = "棋盘格可见" if found else "未检测到棋盘格"
                cv2.putText(frame, f"{len(images)}/{args.count}  {hint}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("calib", frame)
                key = cv2.waitKey(30) & 0xFF
                if key == 27:
                    break
                if key == 32 and found:
                    images.append(frame.copy())
            cap.release()
            cv2.destroyAllWindows()
            if not images:
                print("未采集到有效图像", file=sys.stderr)
                return 1
        elif args.images_dir:
            d = Path(args.images_dir)
            images = [cv2.imread(str(p)) for p in sorted(d.glob("*")) if cv2.imread(str(p)) is not None]
            if not images:
                print(f"目录 {d} 没有可读图像", file=sys.stderr)
                return 1
        else:
            print("需要 --chessboard --images-dir/--camera，或 --from-points", file=sys.stderr)
            return 2

        h, err, size = from_chessboard(images, pattern, args.square_mm)
        save_homography(out, h, err, size, "chessboard", len(images) * pattern[0] * pattern[1])
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[错误] {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

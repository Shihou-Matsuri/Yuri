"""枚举摄像头：列出 DirectShow 设备名（通过 ffmpeg）与 OpenCV 可打开索引。

用法:
  python tools/list_cameras.py
  python tools/list_cameras.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

import cv2


def dshow_device_names() -> list[str]:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []
    names: list[str] = []
    for line in (proc.stderr or "").splitlines():
        m = re.search(r'"([^"]+)"\s+\(video\)', line)
        if m:
            names.append(m.group(1))
    return names


def opencv_indexes(max_index: int = 8) -> list[dict]:
    found: list[dict] = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, frame = cap.read()
            found.append({"index": i, "shape": list(frame.shape) if ok else None})
        cap.release()
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    names = dshow_device_names()
    idxs = opencv_indexes()

    if args.json:
        print(json.dumps({"devices": names, "opencv": idxs}, ensure_ascii=False, indent=2))
        return

    print("DirectShow 视频设备（按 ffmpeg 枚举顺序，通常对应 OpenCV 索引 0,1,2,...）:")
    for n in names:
        print("  -", n)
    print("\nOpenCV 可打开索引:")
    for it in idxs:
        print(f"  - index={it['index']} shape={it['shape']}")
    print("\n提示: 本机罗技 C922 通常为 index=1，可在 configs/default.json 的 camera.index 中修改。")


if __name__ == "__main__":
    sys.exit(main())

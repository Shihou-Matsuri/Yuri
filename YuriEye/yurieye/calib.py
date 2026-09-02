"""相机内参标定（棋盘格）、去畸变、像素-毫米换算。

标定需要打印一张棋盘格，从多个角度拍摄 10~20 张；
也可用 tools/calib_camera.py 从摄像头逐张采集。
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

DEFAULT_CALIB_PATH = Path(__file__).resolve().parents[1] / "configs" / "camera_calibration.json"


class CameraCalibration:
    def __init__(self, k=None, dist=None, image_size=None, rms=None):
        self.k = np.asarray(k, dtype=np.float64) if k is not None else None
        self.dist = np.asarray(dist, dtype=np.float64) if dist is not None else None
        self.image_size = tuple(image_size) if image_size else None
        self.rms = rms

    @classmethod
    def load(cls, path=DEFAULT_CALIB_PATH) -> "CameraCalibration":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            k=data.get("k"),
            dist=data.get("dist"),
            image_size=data.get("image_size"),
            rms=data.get("rms"),
        )

    def save(self, path=DEFAULT_CALIB_PATH) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "k": None if self.k is None else self.k.tolist(),
            "dist": None if self.dist is None else self.dist.tolist(),
            "image_size": list(self.image_size) if self.image_size else None,
            "rms": self.rms,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def undistort(self, bgr: np.ndarray) -> np.ndarray:
        if self.k is None or self.dist is None:
            return bgr
        h, w = bgr.shape[:2]
        return cv2.undistort(bgr, self.k, self.dist)


def find_chessboard_corners(gray: np.ndarray, pattern=(9, 6)):
    """在灰度图上找棋盘格角点，返回角点或 None。"""
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_FAST_CHECK
    found, corners = cv2.findChessboardCorners(gray, pattern, flags)
    if not found:
        return None
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    return corners


def calibrate_from_images(images: list[np.ndarray], pattern=(9, 6), square_mm: float = 25.0) -> CameraCalibration:
    """从多张含棋盘格的图像标定内参。"""
    if not images:
        raise ValueError("至少需要一张含棋盘格的图像")
    objp = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2) * square_mm

    obj_points: list[np.ndarray] = []
    img_points: list[np.ndarray] = []
    image_size = None
    for img in images:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = find_chessboard_corners(gray, pattern)
        if corners is None:
            continue
        obj_points.append(objp)
        img_points.append(corners.reshape(-1, 2))
        image_size = (gray.shape[1], gray.shape[0])

    if len(obj_points) < 3:
        raise ValueError(f"有效棋盘格视图不足（{len(obj_points)}/3），请调整角度/光照后重试")

    rms, k, dist, _rvecs, _tvecs = cv2.calibrateCamera(obj_points, img_points, image_size, None, None)
    return CameraCalibration(k=k, dist=dist, image_size=image_size, rms=float(rms))


def estimate_distance_from_area(area_px: float, real_size_mm: float, focal_px: float) -> float | None:
    """由可见面像素面积估算相机到立方体的距离（近似，正面视角时较准）。

    假设可见面近似正方形且正对相机：面宽 px ≈ sqrt(area_px)，
    距离 ≈ focal_px * real_size_mm / 面宽 px。
    """
    if area_px <= 0 or real_size_mm <= 0 or focal_px <= 0:
        return None
    face_px = float(np.sqrt(area_px))
    return focal_px * real_size_mm / face_px

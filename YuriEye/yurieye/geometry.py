"""立方体几何校验：判断轮廓是否像正方体的可见轮廓。"""
from __future__ import annotations

import cv2
import numpy as np


def approx_poly(contour, epsilon_ratio: float = 0.03) -> np.ndarray:
    """多边形简化。epsilon 略大以抑制掩码边缘噪声，更接近真实立方体轮廓。"""
    peri = cv2.arcLength(contour, True)
    return cv2.approxPolyDP(contour, epsilon_ratio * peri, True)


def is_cube_like(
    contour: np.ndarray,
    aspect_range=(0.4, 2.5),
    min_solidity: float = 0.85,
    min_fill_ratio: float = 0.45,
    min_vertices: int = 4,
    max_vertices: int = 8,
) -> tuple[bool, dict]:
    """判断轮廓是否呈立方体可见轮廓。

    立方体任意姿态下的轮廓是凸多边形（4~6 个顶点，透视下最多 6），
    整体外接矩形接近方形，且填充率较高。

    返回 (ok, scores)，scores 含 solidity / fill_ratio / aspect / n_vertices。
    """
    area = cv2.contourArea(contour)
    scores = {"solidity": 0.0, "fill_ratio": 0.0, "aspect": 99.0, "n_vertices": 0}
    if area <= 0:
        return False, scores

    hull_area = cv2.contourArea(cv2.convexHull(contour))
    scores["solidity"] = area / hull_area if hull_area > 0 else 0.0

    (rw, rh) = cv2.minAreaRect(contour)[1]
    if rw <= 0 or rh <= 0:
        return False, scores
    scores["fill_ratio"] = area / (rw * rh)
    w, h = max(rw, rh), min(rw, rh)
    scores["aspect"] = w / h if h > 0 else 99.0

    approx = approx_poly(contour)
    scores["n_vertices"] = len(approx)

    # 凸性用 solidity 阈值表达（真实掩码常因阴影/出画存在轻微凹陷），
    # 不再做 isContourConvex 硬性检查；误检由覆盖率/面积/宽高比共同兜底。
    ok = (
        aspect_range[0] <= scores["aspect"] <= aspect_range[1]
        and scores["solidity"] >= min_solidity
        and scores["fill_ratio"] >= min_fill_ratio
        and min_vertices <= scores["n_vertices"] <= max_vertices
    )
    return ok, scores

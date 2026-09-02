"""颜色立方体检测器（经典 CV 基线）。

管线：HSV 分色 -> 形态学清理 -> 轮廓 -> 立方体几何校验 -> 掩码覆盖率 ->
同物去重 -> （可选）同尺寸一致性过滤。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .color_utils import hsv_mask
from .geometry import approx_poly, is_cube_like


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, w, h
    center: tuple[int, int]
    area_px: float
    contour: np.ndarray = field(repr=False)
    approx: np.ndarray = field(repr=False)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "bbox": list(self.bbox),
            "center": list(self.center),
            "area_px": round(self.area_px, 1),
        }


class CubeDetector:
    """基于 HSV 颜色分割 + 几何校验的检测器。"""

    def __init__(self, colors: dict, geometry: dict | None = None):
        if not colors:
            raise ValueError("colors 配置不能为空")
        self.colors = colors
        self.geometry = geometry or {}

    def _morph(self, mask: np.ndarray) -> np.ndarray:
        open_size = int(self.geometry.get("morph_open_size", 5))
        close_size = int(self.geometry.get("morph_close_size", 9))
        if open_size > 1:
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((open_size, open_size), np.uint8))
        if close_size > 1:
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close_size, close_size), np.uint8))
        return mask

    def detect(self, bgr: np.ndarray) -> list[Detection]:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        detections: list[Detection] = []
        min_area = float(self.geometry.get("min_area_px", 400))
        max_area = float(self.geometry.get("max_area_px", 200_000))

        for label, spec in self.colors.items():
            mask = hsv_mask(hsv, spec.get("hsv_ranges") or [])
            mask = self._morph(mask)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                area = cv2.contourArea(c)
                if area < min_area or area > max_area:
                    continue
                ok, _scores = is_cube_like(c, **self._geo_kwargs())
                if not ok:
                    continue
                # 掩码覆盖率：轮廓内像素属于该颜色掩码的比例
                cmask = np.zeros(mask.shape, dtype=np.uint8)
                cv2.drawContours(cmask, [c], -1, 255, -1)
                cnt_px = int(np.count_nonzero(cmask))
                if cnt_px <= 0:
                    continue
                coverage = float(np.count_nonzero(cv2.bitwise_and(cmask, mask))) / cnt_px
                if coverage < float(self.geometry.get("min_coverage", 0.6)):
                    continue
                x, y, w, h = cv2.boundingRect(c)
                confidence = min(1.0, coverage * (0.6 + 0.4 * _scores["solidity"]))
                detections.append(
                    Detection(
                        label=label,
                        confidence=confidence,
                        bbox=(int(x), int(y), int(w), int(h)),
                        center=(int(x + w // 2), int(y + h // 2)),
                        area_px=area,
                        contour=c,
                        approx=approx_poly(c),
                    )
                )

        detections = self._dedupe(detections)
        detections = self._uniform_size_filter(detections)
        return detections

    def _geo_kwargs(self) -> dict:
        return {
            "aspect_range": tuple(self.geometry.get("aspect_range", (0.3, 3.5))),
            "min_solidity": float(self.geometry.get("min_solidity", 0.85)),
            "min_fill_ratio": float(self.geometry.get("min_fill_ratio", 0.45)),
            "min_vertices": int(self.geometry.get("min_vertices", 4)),
            "max_vertices": int(self.geometry.get("max_vertices", 8)),
        }

    def _dedupe(self, detections: list[Detection]) -> list[Detection]:
        """同一物体可能命中多个颜色掩码，保留置信度最高者。"""
        dup_dist = int(self.geometry.get("dup_distance_px", 40))
        ordered = sorted(detections, key=lambda d: d.confidence, reverse=True)
        kept: list[Detection] = []
        for d in ordered:
            if any(
                abs(d.center[0] - k.center[0]) < dup_dist
                and abs(d.center[1] - k.center[1]) < dup_dist
                for k in kept
            ):
                continue
            kept.append(d)
        return kept

    def _uniform_size_filter(self, detections: list[Detection]) -> list[Detection]:
        """可选：相同大小的立方体在相近深度下面积应接近，据此剔除离群误检。"""
        if not self.geometry.get("enforce_uniform_size", False) or len(detections) < 2:
            return detections
        areas = np.array([d.area_px for d in detections])
        med = float(np.median(areas))
        if med <= 0:
            return detections
        tol = float(self.geometry.get("size_tolerance", 0.6))
        return [d for d in detections if med * (1 - tol) <= d.area_px <= med * (1 + tol)]

"""可视化：画检测框、标签、调试视图。"""
from __future__ import annotations

import cv2
import numpy as np

from .color_utils import hsv_mask
from .detector import Detection


def _bgr(color_rgb) -> tuple[int, int, int]:
    if color_rgb is None:
        return (255, 255, 255)
    r, g, b = int(color_rgb[0]), int(color_rgb[1]), int(color_rgb[2])
    return (b, g, r)


def draw_detections(frame: np.ndarray, detections: list[Detection], colors_cfg: dict) -> np.ndarray:
    out = frame.copy()
    for d in detections:
        color = _bgr(colors_cfg.get(d.label, {}).get("rgb"))
        x, y, w, h = d.bbox
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        cv2.circle(out, d.center, 4, color, -1)
        label = f"{d.label} {d.confidence:.2f}"
        cv2.putText(out, label, (x, max(y - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return out


def overlay_masks(frame: np.ndarray, colors_cfg: dict, alpha: float = 0.35) -> np.ndarray:
    """叠加各颜色掩码，用于调试（观察分割效果）。"""
    out = frame.copy()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    for label, spec in colors_cfg.items():
        mask = hsv_mask(hsv, spec.get("hsv_ranges") or [])
        if not np.any(mask):
            continue
        color = _bgr(spec.get("rgb", (255, 255, 255)))
        colored = np.zeros_like(frame)
        colored[mask > 0] = color
        out = cv2.addWeighted(out, 1.0, colored, alpha, 0)
    return out

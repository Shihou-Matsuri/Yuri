"""HSV 颜色工具：范围掩码、取色采样、范围合并。"""
from __future__ import annotations

import cv2
import numpy as np

# 采样时只统计有意义的彩色像素（排除白/黑，其 H 值无意义）
SAT_MIN = 60
VAL_MIN = 40


def hsv_mask(hsv: np.ndarray, ranges: list) -> np.ndarray:
    """根据一组 HSV 范围生成二值掩码。

    ranges: list of [lower, upper]，lower/upper 各为 [H,S,V]（OpenCV 的 H∈[0,180]）。
    """
    if not ranges:
        return np.zeros(hsv.shape[:2], dtype=np.uint8)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for low, high in ranges:
        part = cv2.inRange(hsv, np.asarray(low, dtype=np.uint8), np.asarray(high, dtype=np.uint8))
        mask = cv2.bitwise_or(mask, part)
    return mask


def _cluster_hue_ranges(hues: np.ndarray, s_lo: int, s_hi: int, v_lo: int, v_hi: int,
                        gap_threshold: int = 90) -> list[list[list[int]]]:
    """把一组 H 值按最大圆周间隙聚成 1~2 段 HSV 范围。

    解决红色在 0/180 附近的回绕：若 H 值同时出现在低端与高端（内部存在大间隙），
    拆成两段；否则作为连续单段。
    """
    if hues.size == 0:
        return []
    uniq = np.sort(np.unique(hues))
    n = uniq.size
    if n == 1:
        h = int(uniq[0])
        return [[[h, s_lo, v_lo], [h, s_hi, v_hi]]]

    diffs = np.empty(n)
    diffs[:-1] = np.diff(uniq)
    diffs[-1] = int(uniq[0]) + 180 - int(uniq[-1])  # 回绕间隙
    j = int(np.argmax(diffs))
    if j < n - 1 and diffs[j] >= gap_threshold:
        # 内部大间隙：拆两段
        return [
            [[int(uniq[0]), s_lo, v_lo], [int(uniq[j]), s_hi, v_hi]],
            [[int(uniq[j + 1]), s_lo, v_lo], [int(uniq[-1]), s_hi, v_hi]],
        ]
    # 连续单段（最大间隙在回绕处）
    return [[[int(uniq[0]), s_lo, v_lo], [int(uniq[-1]), s_hi, v_hi]]]


def sample_patch_hsv(bgr: np.ndarray, center, radius: int = 8) -> dict | None:
    """采样点击点附近矩形区域内的 HSV 统计。

    仅统计 S>=SAT_MIN 且 V>=VAL_MIN 的像素（排除白/黑噪声），
    并返回聚类后的 ranges（正确处理红色回绕）。
    画面中该区域没有彩色像素时返回 None。
    """
    h, w = bgr.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    x0, y0 = max(cx - radius, 0), max(cy - radius, 0)
    x1, y1 = min(cx + radius + 1, w), min(cy + radius + 1, h)
    patch = bgr[y0:y1, x0:x1]
    if patch.size == 0:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    h_chan, s_chan, v_chan = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    valid = (s_chan >= SAT_MIN) & (v_chan >= VAL_MIN)
    if not np.any(valid):
        return None
    h_v, s_v, v_v = h_chan[valid], s_chan[valid], v_chan[valid]
    ranges = _cluster_hue_ranges(
        h_v,
        int(s_v.min()), int(s_v.max()),
        int(v_v.min()), int(v_v.max()),
    )
    return {
        "ranges": ranges,
        "h_min": int(h_v.min()), "h_max": int(h_v.max()),
        "s_min": int(s_v.min()), "s_max": int(s_v.max()),
        "v_min": int(v_v.min()), "v_max": int(v_v.max()),
        "h_mean": float(h_v.mean()), "s_mean": float(s_v.mean()),
        "v_mean": float(v_v.mean()),
        "count": int(valid.sum()),
    }


def merge_samples(samples: list[dict]) -> list[list[list[int]]]:
    """把多次采样转为 HSV 范围列表（各采样范围取并集，检测时整体求或）。

    不做跨采样的 H min/max 合并，避免红色 0/180 回绕导致范围被错误放大；
    每次采样的回绕已在 sample_patch_hsv 内处理。去除完全重复的范围。
    """
    ranges: list[list[list[int]]] = []
    seen: set[tuple] = set()
    for s in samples:
        for r in s.get("ranges") or []:
            key = (tuple(r[0]), tuple(r[1]))
            if key not in seen:
                seen.add(key)
                ranges.append(r)
    return ranges

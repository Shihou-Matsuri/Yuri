"""感知封装：把 YuriEye 检测结果转成任务空间 Block（mm 坐标）。

管线：相机帧 → YuriEye 检测（ML YOLO 优先，HSV 基线兜底）→ 像素中心
      → 单应矩阵 → 桌面 mm 坐标 → Block 列表。

缺失任一环节（yurieye 不在、无单应、无相机/权重）→ 抛 :class:`PerceptionUnavailable`，
上层（state_machine / CLI）捕获后自动回退手动模式，不影响抓取主流程。

- 本模块是"后期摄像头 + ML 自动识别"的接入缝：相机/检测/坐标变换全部依赖注入，
  便于离线测试与逐段替换。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .config import ArmConfig
from .planner import Block

DEFAULT_HOMOGRAPHY_PATH = Path(__file__).resolve().parents[1] / "configs" / "homography.json"


class PerceptionUnavailable(RuntimeError):
    """感知链路不可用（原因见 message），上层应回退手动模式。"""


def _find_yurieye_path(cfg_path: str | None) -> Path | None:
    if cfg_path:
        p = Path(cfg_path)
        return p if p.is_dir() else None
    # 自动探测：YuriArm 与 YuriEye 是同级目录
    candidate = Path(__file__).resolve().parents[2] / "YuriEye"
    return candidate if candidate.is_dir() else None


def _import_yurieye(cfg_path: str | None):
    """惰性导入 yurieye；失败返回 None（调用方决定降级）。"""
    root = _find_yurieye_path(cfg_path)
    if root is None:
        return None
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        import yurieye  # noqa: F401
        return yurieye
    except Exception:
        return None


class Homography:
    """图像像素 ↔ 桌面 mm 的单应变换（由 tools/calib_homography.py 生成）。"""

    def __init__(self, h: list[list[float]], image_size: tuple[int, int] | None = None,
                 reproj_error: float | None = None):
        try:
            import numpy as np
            self._h = np.asarray(h, dtype=np.float64)
        except ImportError as e:  # pragma: no cover
            raise PerceptionUnavailable("需要 numpy") from e
        self.image_size = image_size
        self.reproj_error = reproj_error

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Homography":
        p = Path(path) if path else DEFAULT_HOMOGRAPHY_PATH
        if not p.is_file():
            raise PerceptionUnavailable(
                f"未找到单应文件 {p}，请先运行 tools/calib_homography.py 标定"
            )
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        size = data.get("image_size")
        return cls(
            h=data["H"],
            image_size=tuple(size) if size else None,
            reproj_error=data.get("reproj_error"),
        )

    def pixel_to_mm(self, x_px: float, y_px: float) -> tuple[float, float]:
        try:
            import numpy as np
            src = np.array([[[x_px, y_px]]], dtype=np.float64)
            dst = cv2_perspective_transform(self._h, src)
            return float(dst[0][0][0]), float(dst[0][0][1])
        except Exception as e:
            raise PerceptionUnavailable(f"单应变换失败: {e}") from e


def cv2_perspective_transform(h, src):
    """独立实现 cv2.perspectiveTransform，避免硬依赖 cv2（可被测试替换）。"""
    import numpy as np
    pts = np.asarray(src, dtype=np.float64).reshape(-1, 2)
    ones = np.ones((pts.shape[0], 1), dtype=np.float64)
    hom = np.hstack([pts, ones]) @ h.T
    hom = hom / hom[:, 2:3]
    return hom[:, :2].reshape(src.shape)


class BlockDetector:
    """检测后端接口（像素 → 颜色/bbox/置信度）。"""

    def detect(self, bgr) -> list[dict[str, Any]]:
        """返回 [{"label", "confidence", "bbox": [x1,y1,x2,y2]}, ...]"""
        raise NotImplementedError


class YurieyeDetector(BlockDetector):
    """包装 YuriEye 的检测器：优先 YOLO（ultralytics），否则 HSV 基线。"""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self._ml = None
        self._cv = None
        self._colors_cfg = None

    def _load(self):
        ye = _import_yurieye(self.cfg.get("yurieye_path"))
        if ye is None:
            raise PerceptionUnavailable("未找到 yurieye 包（YuriEye 目录不存在或不可导入）")
        if self._ml is None:
            weights = self.cfg.get("ml_weights")
            if weights and Path(weights).is_file():
                try:
                    from ultralytics import YOLO
                    self._ml = YOLO(str(weights))
                except Exception:
                    self._ml = None
        if self._cv is None:
            from yurieye.config import load_config as ye_load_config
            from yurieye.detector import CubeDetector
            self._colors_cfg = ye_load_config()["colors"]
            geo = {"min_area_px": self.cfg.get("cube_min_area_px", 400.0)}
            self._cv = CubeDetector(self._colors_cfg, geo)

    def detect(self, bgr) -> list[dict[str, Any]]:
        self._load()
        if self._ml is not None:
            res = self._ml.predict(bgr, conf=float(self.cfg.get("ml_conf", 0.25)),
                                   verbose=False)[0]
            out = []
            for b in res.boxes:
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                out.append({
                    "label": res.names[int(b.cls)],
                    "confidence": float(b.conf),
                    "bbox": [x1, y1, x2, y2],
                })
            if out:
                return out
        dets = self._cv.detect(bgr)
        return [d.to_dict() | {"bbox": [d.bbox[0], d.bbox[1], d.bbox[0] + d.bbox[2], d.bbox[1] + d.bbox[3]]}
                for d in dets]


def detections_to_blocks(detections: list[dict[str, Any]], homography: Homography,
                         cube_size_mm: float = 30.0, label_prefix: str = "") -> list[Block]:
    """像素检测结果 → mm 坐标 Block 列表（供测试直接调用）。"""
    blocks: list[Block] = []
    for i, d in enumerate(detections):
        x1, y1, x2, y2 = d["bbox"]
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        mx, my = homography.pixel_to_mm(cx, cy)
        blocks.append(Block(
            x_mm=mx, y_mm=my, color=d["label"], z_mm=cube_size_mm,
            score=float(d.get("confidence", 0.0)),
            label=f"{label_prefix}{i}",
        ))
    return blocks


def verify_pick(initial: list[Block], current: list[Block], picked: Block,
                tolerance_mm: float = 10.0) -> dict[str, Any]:
    """验证一次抓取：目标消失，且其它方块（尤其非目标）位置未变。"""
    def near(a: Block, b: Block) -> bool:
        return abs(a.x_mm - b.x_mm) <= tolerance_mm and abs(a.y_mm - b.y_mm) <= tolerance_mm

    target_gone = not any(near(b, picked) and b.color == picked.color for b in current)
    moved = []
    for b in initial:
        if near(b, picked) and b.color == picked.color:
            continue
        if not any(near(b, c) and c.color == b.color for c in current):
            moved.append(b.to_dict())
    return {
        "target_removed": bool(target_gone),
        "others_moved": moved,
        "ok": bool(target_gone and not moved),
    }


class Perception:
    """感知门面：scan_blocks() 返回桌面 Block 列表；不可用时抛 PerceptionUnavailable。"""

    def __init__(self, config: ArmConfig,
                 detector: BlockDetector | None = None,
                 homography: Homography | None = None,
                 frame_source: Callable[[], Any] | None = None):
        self.config = config
        pcfg = config.perception
        self._detector = detector or YurieyeDetector(pcfg)
        self._homography = homography
        self._frame_source = frame_source

    def scan_blocks(self) -> list[Block]:
        pcfg = self.config.perception
        if not pcfg.get("enabled", False):
            raise PerceptionUnavailable("perception.enabled=false（配置未开启感知）")
        homography = self._homography or Homography.load(pcfg.get("homography_path"))
        frame = self._frame_source() if self._frame_source else self._read_camera(pcfg)
        dets = self._detector.detect(frame)
        return detections_to_blocks(dets, homography,
                                    cube_size_mm=float(self.config.blocks.get("cube_size_mm", 30.0)))

    @staticmethod
    def _read_camera(pcfg: dict[str, Any]):
        """打开摄像头读一帧（复用 yurieye.camera 的设置逻辑，失败时抛不可用）。"""
        ye = _import_yurieye(pcfg.get("yurieye_path"))
        if ye is None:
            raise PerceptionUnavailable("未找到 yurieye 包，无法打开摄像头")
        cam = ye.camera.Camera(index=int(pcfg.get("camera_index", 1)))
        try:
            ok, frame = cam.read()
            if not ok or frame is None:
                raise PerceptionUnavailable("摄像头读帧失败（可能被占用）")
            return frame
        finally:
            cam.release()

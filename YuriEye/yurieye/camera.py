"""摄像头封装：Windows DirectShow 后端、分辨率/曝光/白平衡设置。"""
from __future__ import annotations

import cv2
import numpy as np

DEFAULT_BACKEND = getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)


class CameraError(RuntimeError):
    pass


class Camera:
    """对 cv2.VideoCapture 的轻量封装。

    C922 在 DirectShow 后端下可设置分辨率、手动曝光与白平衡；
    不同型号对 CAP_PROP_AUTO_EXPOSURE / CAP_PROP_EXPOSURE 的语义可能不同，
    若手动设置不生效，保留自动模式即可。
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        backend: int = DEFAULT_BACKEND,
        auto_exposure: bool = True,
        exposure: float = -5.0,
        auto_white_balance: bool = True,
        wb_temperature: int = 4600,
    ):
        self.index = index
        self.cap = cv2.VideoCapture(index, backend)
        if not self.cap.isOpened():
            raise CameraError(f"无法打开摄像头 index={index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        if not auto_exposure:
            # 0.25=关闭自动曝光（多数 DirectShow 摄像头），随后写入手动曝光值
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        if not auto_white_balance:
            self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)
            self.cap.set(cv2.CAP_PROP_WB_TEMPERATURE, wb_temperature)

    def read(self) -> tuple[bool, np.ndarray]:
        return self.cap.read()

    def info(self) -> dict:
        return {
            "index": self.index,
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": self.cap.get(cv2.CAP_PROP_FPS),
        }

    def release(self) -> None:
        self.cap.release()

"""Windows XInput controller backend for the camera car.

The GUI polls this module directly with XInput, so the packaged executable
does not need pygame or another third-party gamepad library.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

ERROR_SUCCESS = 0
ERROR_DEVICE_NOT_CONNECTED = 1167

BTN_A = 0x1000
BTN_B = 0x2000
BTN_X = 0x4000
BTN_Y = 0x8000
BTN_LB = 0x0100
BTN_RB = 0x0200
BTN_DPAD_UP = 0x0001
BTN_DPAD_DOWN = 0x0002


class XInputGamepad(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XInputState(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XInputGamepad),
    ]


class GamepadError(RuntimeError):
    pass


class GamepadNotConnectedError(GamepadError):
    pass


@dataclass(frozen=True)
class GamepadSnapshot:
    left_x: float
    left_y: float
    right_x: float
    right_y: float
    left_trigger: float
    right_trigger: float
    buttons: int

    @property
    def moving(self) -> bool:
        return abs(self.left_x) > 0.12 or abs(self.left_y) > 0.12 or abs(self.right_x) > 0.12


def normalize_axis(value: int) -> float:
    return max(-1.0, min(1.0, value / 32767.0))


def _load_xinput() -> ctypes.WinDLL:
    last_error: Exception | None = None
    for name in ("XInput1_4.dll", "xinput1_3.dll", "XInput9_1_0.dll"):
        try:
            dll = ctypes.WinDLL(name)
            dll.XInputGetState.argtypes = [
                ctypes.c_uint,
                ctypes.POINTER(XInputState),
            ]
            dll.XInputGetState.restype = ctypes.c_uint
            return dll
        except OSError as exc:
            last_error = exc
    raise GamepadError(f"无法加载 XInput: {last_error}")


class XInputController:
    def __init__(self, index: int = 0) -> None:
        self.index = index
        self._dll = _load_xinput()

    def read(self) -> GamepadSnapshot:
        state = XInputState()
        result = self._dll.XInputGetState(self.index, ctypes.byref(state))
        if result == ERROR_DEVICE_NOT_CONNECTED:
            raise GamepadNotConnectedError(f"手柄 {self.index} 未连接")
        if result != ERROR_SUCCESS:
            raise GamepadError(f"XInputGetState 失败: {result}")

        gamepad = state.Gamepad
        return GamepadSnapshot(
            left_x=normalize_axis(gamepad.sThumbLX),
            left_y=normalize_axis(gamepad.sThumbLY),
            right_x=normalize_axis(gamepad.sThumbRX),
            right_y=normalize_axis(gamepad.sThumbRY),
            left_trigger=gamepad.bLeftTrigger / 255.0,
            right_trigger=gamepad.bRightTrigger / 255.0,
            buttons=gamepad.wButtons,
        )

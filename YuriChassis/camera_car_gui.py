"""Camera car control window.

The window keeps the serial port open and lets the user drive the chassis with
buttons or keyboard keys. Closing the window stops all wheels and turns torque
off before releasing the port.
"""

from __future__ import annotations

import argparse
import tkinter as tk
from contextlib import suppress
from tkinter import messagebox, ttk
from typing import Any

import camera_car_drive as controller
from camera_car_gamepad import BTN_A, BTN_B, BTN_Y, GamepadNotConnectedError, XInputController


class CameraCarGUI:
    def __init__(self, root: tk.Tk, port: str, baud: int) -> None:
        self.root = root
        self.root.title("Camera Car Control")
        self.root.geometry("620x520")
        self.root.configure(bg="#f5f6f8")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.config = controller.CarConfig()
        self.port = port
        self.baud = baud
        self.ports: list[str] = []
        self.input_mode_var = tk.StringVar(value="键盘")
        self.gamepad_status_var = tk.StringVar(value="手柄未连接")
        self.gamepad: XInputController | None = None
        self.gamepad_connected = False
        self._polling = True
        self.serial: Any | None = None
        self.ready = False
        self.active_motion: controller.Motion | None = None

        self.port_var = tk.StringVar(value=port)
        self.status_var = tk.StringVar(value=f"正在连接 {port}")
        self.mapping_var = tk.StringVar(
            value=f"前中=ID{self.config.front_id}  "
            f"后左=ID{self.config.rear_left_id}  "
            f"后右=ID{self.config.rear_right_id}"
        )
        self.reverse_rear_left_var = tk.BooleanVar(
            value=self.config.directions.get(self.config.rear_left_id, 1) == -1
        )
        self.reverse_rear_right_var = tk.BooleanVar(
            value=self.config.directions.get(self.config.rear_right_id, 1) == -1
        )
        self._build()
        self._refresh_ports()
        self._bind_keys()
        self._init_gamepad()
        self._connect()
        self._poll_gamepad()

    def _build(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Car.TButton",
            font=("Segoe UI", 13),
            padding=(18, 12),
        )
        style.configure(
            "Small.TButton",
            font=("Segoe UI", 10),
            padding=(8, 4),
        )

        top = ttk.Frame(self.root, padding=(18, 14, 18, 6))
        top.pack(fill="x")
        ttk.Label(
            top,
            text="Camera Car Control",
            font=("Segoe UI", 20, "bold"),
            background="#f5f6f8",
        ).pack(anchor="w")
        ttk.Label(
            top,
            text=self.mapping_var.get(),
            font=("Segoe UI", 11),
            background="#f5f6f8",
        ).pack(anchor="w", pady=(7, 0))

        ports = ttk.Frame(self.root, padding=(18, 4))
        ports.pack(fill="x")
        ttk.Label(
            ports,
            text="串口",
            font=("Segoe UI", 11),
            background="#f5f6f8",
        ).pack(side="left", padx=(0, 6))
        self.port_combo = ttk.Combobox(
            ports,
            textvariable=self.port_var,
            width=13,
            state="readonly",
        )
        self.port_combo.pack(side="left", padx=(0, 8))
        ttk.Button(
            ports,
            text="刷新",
            style="Small.TButton",
            command=self._refresh_ports,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            ports,
            text="连接",
            style="Small.TButton",
            command=self.connect_selected,
        ).pack(side="left")

        mode = ttk.Frame(self.root, padding=(18, 4))
        mode.pack(fill="x")
        ttk.Label(
            mode,
            text="控制",
            font=("Segoe UI", 11),
            background="#f5f6f8",
        ).pack(side="left", padx=(0, 6))
        ttk.Radiobutton(
            mode,
            text="键盘",
            variable=self.input_mode_var,
            value="键盘",
            command=self._on_mode_change,
        ).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            mode,
            text="手柄",
            variable=self.input_mode_var,
            value="手柄",
            command=self._on_mode_change,
        ).pack(side="left", padx=(0, 14))
        ttk.Label(
            mode,
            textvariable=self.gamepad_status_var,
            font=("Segoe UI", 10),
            background="#f5f6f8",
        ).pack(side="left")

        panel = ttk.Frame(self.root, padding=(18, 12))
        panel.pack(fill="both", expand=True)

        self._make_button(panel, "前", controller.Motion.FORWARD, "W", 0, 1)
        self._make_button(panel, "左", controller.Motion.LEFT, "A", 1, 0)
        self._make_button(panel, "停", controller.Motion.STOP, "空格", 1, 1)
        self._make_button(panel, "右", controller.Motion.RIGHT, "D", 1, 2)
        self._make_button(panel, "后", controller.Motion.BACKWARD, "S", 2, 1)

        lower = ttk.Frame(self.root, padding=(18, 8))
        lower.pack(fill="x")
        self._make_button(lower, "左旋", controller.Motion.ROTATE_LEFT, "Z", 0, 0)
        self._make_button(lower, "右旋", controller.Motion.ROTATE_RIGHT, "X", 0, 1)

        adjust = ttk.Frame(self.root, padding=(18, 8))
        adjust.pack(fill="x")
        ttk.Checkbutton(
            adjust,
            text="后左反向 ID6",
            variable=self.reverse_rear_left_var,
            command=self._apply_reverse_toggles,
        ).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(
            adjust,
            text="后右反向 ID4",
            variable=self.reverse_rear_right_var,
            command=self._apply_reverse_toggles,
        ).pack(side="left")

        safety = ttk.Frame(self.root, padding=(18, 8))
        safety.pack(fill="x")
        estop = ttk.Button(
            safety,
            text="急停  E",
            style="Car.TButton",
            command=self.estop,
        )
        estop.pack(side="left", padx=(0, 10))
        ttk.Button(
            safety,
            text="退出  Q",
            style="Car.TButton",
            command=self.close,
        ).pack(side="left")

        status = ttk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 11),
            padding=(18, 10),
            background="#f5f6f8",
        )
        status.pack(fill="x", side="bottom")

    def _make_button(
        self,
        parent: ttk.Frame,
        label: str,
        motion: controller.Motion,
        key: str,
        row: int,
        column: int,
    ) -> None:
        button = ttk.Button(
            parent,
            text=f"{label}  {key}",
            style="Car.TButton",
            command=lambda: self.send_motion(motion),
        )
        button.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=5,
            pady=5,
        )
        button.bind("<ButtonPress>", lambda _event: self.send_motion(motion))
        button.bind("<ButtonRelease>", lambda _event: self.stop())

        for col in range(3):
            parent.grid_columnconfigure(col, weight=1, uniform="pad")
        parent.grid_rowconfigure(row, weight=1)

    def _bind_keys(self) -> None:
        for key in ("w", "a", "s", "d", "z", "x"):
            self.root.bind(f"<KeyPress-{key}>", self._on_key_press)
            self.root.bind(f"<KeyRelease-{key}>", self._on_key_release)
        self.root.bind("<KeyPress-space>", self._on_key_press)
        self.root.bind("<KeyPress-e>", self._on_key_press)
        self.root.bind("<KeyPress-q>", self._on_key_press)

    def _init_gamepad(self) -> None:
        try:
            self.gamepad = XInputController()
        except Exception as exc:
            self.gamepad = None
            self.gamepad_status_var.set(f"手柄不可用: {exc}")

    def _on_mode_change(self) -> None:
        self.stop()
        if self.input_mode_var.get() == "手柄":
            self.status_var.set("手柄模式")
        else:
            self.status_var.set("键盘模式")

    def _gamepad_move(self, snapshot: Any) -> None:
        if self.serial is None:
            return
        try:
            self._ensure_ready()
            vx = -snapshot.left_y * self.config.linear_speed_mps
            vy = -snapshot.left_x * self.config.linear_speed_mps
            omega = -snapshot.right_x * self.config.angular_speed_rad_s
            controller.move(self.serial, self.config, vx, vy, omega)
            self.status_var.set(f"手柄: x={vx:.2f} y={vy:.2f} z={omega:.2f}")
        except Exception as exc:
            self.status_var.set(f"手柄发送失败：{exc}")

    def _poll_gamepad(self) -> None:
        if not self._polling:
            return
        if self.gamepad is not None:
            try:
                snapshot = self.gamepad.read()
                connected = True
            except GamepadNotConnectedError:
                snapshot = None
                connected = False
            except Exception as exc:
                snapshot = None
                connected = False
                self.gamepad_status_var.set(f"手柄错误: {exc}")
        else:
            snapshot = None
            connected = False

        if connected:
            self.gamepad_status_var.set("手柄已连接")
        elif self.gamepad_status_var.get() != "手柄未连接":
            self.gamepad_status_var.set("手柄未连接")

        if self.input_mode_var.get() == "手柄" and not connected:
            self.stop()

        if self.input_mode_var.get() == "手柄" and connected and snapshot is not None:
            if snapshot.buttons & BTN_B:
                self.estop()
            elif snapshot.buttons & BTN_A:
                self.stop()
            elif snapshot.buttons & BTN_Y:
                with suppress(Exception):
                    self._ensure_ready()
                self.status_var.set("手柄已恢复")
            elif snapshot.moving:
                self._gamepad_move(snapshot)
            else:
                self.stop()

        self.root.after(30, self._poll_gamepad)

    def _refresh_ports(self) -> None:
        ports = controller.list_serial_ports()
        if self.port not in ports:
            ports.insert(0, self.port)
        if controller.DEFAULT_PORT not in ports:
            ports.append(controller.DEFAULT_PORT)
        self.ports = ports
        self.port_combo["values"] = ports
        if self.port not in ports:
            self.port = ports[0]
        self.port_var.set(self.port)

    def connect_selected(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            self.status_var.set("请选择串口")
            return
        self.port = port
        self._connect()

    def _disconnect_serial(self) -> None:
        if self.serial is None:
            return
        with suppress(Exception):
            controller.stop(self.serial, self.config)
            controller.close_torque(self.serial, self.config)
        with suppress(Exception):
            self.serial.close()
        self.serial = None
        self.ready = False
        self.active_motion = None

    def _connect(self) -> None:
        self._disconnect_serial()
        try:
            self.status_var.set(f"正在连接 {self.port}")
            self.serial = controller.open_serial(self.port, self.baud)
            controller.prepare(self.serial, self.config)
            self.ready = True
            self.status_var.set(f"已连接 {self.port}，可以操作")
        except Exception as exc:
            self.ready = False
            self.status_var.set(f"连接失败：{exc}")
            messagebox.showerror("Camera Car Control", f"无法连接 {self.port}\n{exc}")

    def _ensure_ready(self) -> None:
        if self.ready:
            return
        if self.serial is None:
            raise RuntimeError("串口未连接")
        controller.prepare(self.serial, self.config)
        self.ready = True

    def send_motion(self, motion: controller.Motion) -> None:
        if self.serial is None:
            return
        if self.input_mode_var.get() != "键盘":
            self.status_var.set("请切换到键盘模式")
            return
        try:
            self._ensure_ready()
            controller.command(self.serial, self.config, motion)
            self.active_motion = motion
            self.status_var.set(motion.value)
        except Exception as exc:
            self.status_var.set(f"发送失败：{exc}")

    def stop(self) -> None:
        if self.serial is None:
            return
        try:
            controller.stop(self.serial, self.config)
            self.active_motion = None
            self.status_var.set("停止")
        except Exception as exc:
            self.status_var.set(f"停止失败：{exc}")

    def estop(self) -> None:
        if self.serial is None:
            return
        try:
            controller.stop(self.serial, self.config)
            controller.close_torque(self.serial, self.config)
            self.active_motion = None
            self.ready = False
            self.status_var.set("急停：已停止并关闭扭矩")
        except Exception as exc:
            self.status_var.set(f"急停失败：{exc}")

    def _apply_reverse_toggles(self) -> None:
        self.stop()
        self.config.directions[self.config.rear_left_id] = -1 if self.reverse_rear_left_var.get() else 1
        self.config.directions[self.config.rear_right_id] = -1 if self.reverse_rear_right_var.get() else 1
        left = "是" if self.reverse_rear_left_var.get() else "否"
        right = "是" if self.reverse_rear_right_var.get() else "否"
        self.status_var.set(f"方向设置已更新：后左反={left}，后右反={right}")

    def close(self) -> None:
        self._polling = False
        self._disconnect_serial()
        self.root.destroy()

    def _on_key_press(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        if key == "q":
            self.close()
            return
        if key == "e":
            self.estop()
            return
        if self.input_mode_var.get() != "键盘":
            return
        if key in ("space", ""):
            self.stop()
            return
        motion = controller.KEY_MOTIONS.get(key)
        if motion is not None:
            self.send_motion(motion)

    def _on_key_release(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        if self.input_mode_var.get() != "键盘":
            return
        if key in controller.KEY_MOTIONS and self.active_motion is not None:
            self.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Camera car control window")
    parser.add_argument("--port", default=controller.DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=controller.BAUD)
    args = parser.parse_args()

    root = tk.Tk()
    CameraCarGUI(root, args.port, args.baud)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

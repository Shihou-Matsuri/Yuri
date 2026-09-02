"""YuriArm 指令/结果协议（传输无关）。

命令与结果均为 JSON 可序列化的 dict，本地控制台、TCP 指令服务器、
以及未来的 ESP32-S3 无线执行端共用同一套报文结构（规范见 firmware/protocol.md）。

报文示例（行分隔 JSON）：
    发送: {"id": 1, "cmd": "move_joints", "params": {"targets": {"shoulder_lift": 30.0}, "duration": 2.0}}
    回报: {"id": 1, "ok": true, "result": {"positions": {...}}, "error": null}
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

# 已知指令集合（单点维护；CLI / server / send_command / 未来固件共用）
KNOWN_COMMANDS: dict[str, str] = {
    "ping": "连通性检查",
    "status": "查询连接/标定/姿态状态",
    "connect": "连接机械臂（真机或 mock）",
    "disconnect": "断开连接",
    "calibrate": "交互式标定（仅本机控制台可用）",
    "move_joints": "移动到目标关节角（归一化单位）",
    "move_to_pose": "移动到命名姿态",
    "record_pose": "把当前关节角记录为命名姿态",
    "open_gripper": "张开夹爪",
    "close_gripper": "合拢夹爪（负载判定夹住）",
    "pick": "执行示教-回放拾取周期",
    "home": "回到 home 姿态",
    "estop": "急停：关闭力矩，停止一切运动",
    "resume": "解除急停并恢复力矩",
    "telemetry": "读取遥测（位置/负载/电压/温度）",
    "scan": "用 YuriEye 扫描桌面方块（需感知可用）",
    "run": "执行完整抓取任务状态机",
    "simulate_block": "调试用：mock 后端模拟夹爪间有无方块",
}

# 允许在服务器模式下交互式标定的命令（其余如 calibrate 会拒绝）
_NON_INTERACTIVE_OK = {
    "ping", "status", "connect", "disconnect", "move_joints", "move_to_pose",
    "record_pose", "open_gripper", "close_gripper", "pick", "home", "estop",
    "resume", "telemetry", "scan", "run", "simulate_block",
}


class ProtocolError(ValueError):
    """报文结构或取值非法。"""


@dataclass
class Command:
    """客户端 -> 服务器 的指令。"""

    cmd: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"cmd": self.cmd, "params": self.params, "ts": self.ts}
        if self.id is not None:
            d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Command":
        if not isinstance(d, dict):
            raise ProtocolError("命令必须是 JSON 对象")
        cmd = d.get("cmd")
        if not isinstance(cmd, str) or not cmd:
            raise ProtocolError("缺少字符串字段 'cmd'")
        if cmd not in KNOWN_COMMANDS:
            raise ProtocolError(
                f"未知指令 '{cmd}'（可用: {', '.join(sorted(KNOWN_COMMANDS))}）"
            )
        params = d.get("params", {})
        if not isinstance(params, dict):
            raise ProtocolError("'params' 必须是 JSON 对象")
        return cls(cmd=cmd, params=params, id=d.get("id"), ts=float(d.get("ts", time.time())))

    @classmethod
    def parse(cls, line: str) -> "Command":
        try:
            return cls.from_dict(json.loads(line))
        except json.JSONDecodeError as e:
            raise ProtocolError(f"JSON 解析失败: {e}") from e


@dataclass
class CommandResult:
    """服务器 -> 客户端 的响应。"""

    ok: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok, "result": self.result, "error": self.error}
        if self.id is not None:
            d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CommandResult":
        return cls(ok=bool(d.get("ok")), result=d.get("result", {}), error=d.get("error"), id=d.get("id"))

    @classmethod
    def ok_result(cls, result: dict[str, Any], id: int | str | None = None) -> "CommandResult":
        return cls(ok=True, result=result, id=id)

    @classmethod
    def fail(cls, error: str, id: int | str | None = None) -> "CommandResult":
        return cls(ok=False, error=str(error), id=id)

    def __str__(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


def is_server_safe(cmd: str) -> bool:
    """该指令是否可以在无人值守的服务器/固件模式下执行。"""
    return cmd in _NON_INTERACTIVE_OK

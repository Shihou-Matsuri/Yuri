"""指令分发：把 protocol.Command 映射到具体实现（CLI / REPL / TCP server 共用）。

这是"电脑直接发送指令控制机械臂"的单一行为入口：
外部程序只需按 protocol.py 的报文格式发送 JSON，即可驱动任意后端（真机/mock）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .arm import YuriArm
from .perception import Perception
from .planner import Block, PickPlanner
from .protocol import Command, CommandResult, is_server_safe
from .state_machine import TaskExecutor


@dataclass
class CommandContext:
    """一次会话的依赖集合。"""

    arm: YuriArm
    config: Any
    perception: Perception | None = None
    planner: PickPlanner | None = None
    server_mode: bool = False
    manual_blocks: list[Block] = field(default_factory=list)


def _num(params: dict, key: str, default: float | None = None) -> float | None:
    v = params.get(key, default)
    return None if v is None else float(v)


def _targets(params: dict) -> dict[str, float]:
    t = params.get("targets")
    if not isinstance(t, dict):
        raise ValueError("move_joints 需要 params.targets（关节→目标值 dict）")
    return {k: float(v) for k, v in t.items()}


def _optional_poses(params: dict, keys: list[str]) -> dict[str, str | None]:
    return {k: params.get(k) for k in keys}


def dispatch(ctx: CommandContext, cmd: Command) -> CommandResult:
    """执行单条指令，返回结构化结果。任何异常都被捕获并转为失败结果。"""
    try:
        if ctx.server_mode and not is_server_safe(cmd.cmd):
            return CommandResult.fail(
                f"指令 '{cmd.cmd}' 需要交互输入，服务器模式下拒绝执行（请用控制台）",
                id=cmd.id,
            )
        handler = _HANDLERS.get(cmd.cmd)
        if handler is None:
            return CommandResult.fail(f"未知指令 '{cmd.cmd}'", id=cmd.id)
        result = handler(ctx, cmd.params)
        return CommandResult.ok_result(result, id=cmd.id)
    except Exception as e:  # noqa: BLE001 —— 协议层保证任何错误都返回给调用方
        return CommandResult.fail(f"{type(e).__name__}: {e}", id=cmd.id)


# ------------------------------------------------------------------ handlers
def _h_ping(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return {"pong": True}


def _h_status(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.status()


def _h_connect(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.connect()


def _h_disconnect(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.disconnect()


def _h_calibrate(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.calibrate()


def _h_move_joints(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.move_joints(
        _targets(p),
        duration=_num(p, "duration"),
        max_velocity=_num(p, "max_velocity"),
    )


def _h_move_to_pose(ctx: CommandContext, p: dict) -> dict[str, Any]:
    name = p.get("pose")
    if not isinstance(name, str) or not name:
        raise ValueError("move_to_pose 需要 params.pose（姿态名）")
    return ctx.arm.move_to_pose(name, max_velocity=_num(p, "max_velocity"))


def _h_record_pose(ctx: CommandContext, p: dict) -> dict[str, Any]:
    name = p.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("record_pose 需要 params.name")
    return ctx.arm.record_pose(name)


def _h_open_gripper(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.open_gripper(velocity=_num(p, "velocity"))


def _h_close_gripper(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.close_gripper(max_load=_num(p, "max_load"), timeout=_num(p, "timeout"))


def _h_pick(ctx: CommandContext, p: dict) -> dict[str, Any]:
    poses = _optional_poses(p, ["pick_high", "pick_low", "drop"])
    return ctx.arm.pick(pick_high=poses["pick_high"], pick_low=poses["pick_low"],
                        drop=poses["drop"], max_velocity=_num(p, "max_velocity"))


def _h_home(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.home(max_velocity=_num(p, "max_velocity"))


def _h_estop(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.estop()


def _h_resume(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.resume()


def _h_telemetry(ctx: CommandContext, p: dict) -> dict[str, Any]:
    return ctx.arm.read_telemetry()


def _h_scan(ctx: CommandContext, p: dict) -> dict[str, Any]:
    if ctx.perception is None:
        raise ValueError("未配置感知（perception），无法扫描")
    blocks = ctx.perception.scan_blocks()
    return {"blocks": [b.to_dict() for b in blocks]}


def _h_run(ctx: CommandContext, p: dict) -> dict[str, Any]:
    executor = TaskExecutor(ctx.arm, ctx.config, perception=ctx.perception, planner=ctx.planner)
    targets = p.get("target_colors") or ctx.config.blocks.get("target_colors", [])
    manual = ctx.manual_blocks or []
    if not manual and p.get("blocks"):
        manual = [Block(**b) for b in p["blocks"]]
    report = executor.run(target_colors=list(targets), blocks=manual or None)
    return report.to_dict()


def _h_simulate_block(ctx: CommandContext, p: dict) -> dict[str, Any]:
    from .arm import MockArm
    if not isinstance(ctx.arm.backend, MockArm):
        raise ValueError("simulate_block 仅对 mock 后端有效（真机请用真实方块）")
    present = bool(p.get("present", True))
    ctx.arm.backend.set_block(present)
    return {"block_present": present}


_HANDLERS = {
    "ping": _h_ping,
    "status": _h_status,
    "connect": _h_connect,
    "disconnect": _h_disconnect,
    "calibrate": _h_calibrate,
    "move_joints": _h_move_joints,
    "move_to_pose": _h_move_to_pose,
    "record_pose": _h_record_pose,
    "open_gripper": _h_open_gripper,
    "close_gripper": _h_close_gripper,
    "pick": _h_pick,
    "home": _h_home,
    "estop": _h_estop,
    "resume": _h_resume,
    "telemetry": _h_telemetry,
    "scan": _h_scan,
    "run": _h_run,
    "simulate_block": _h_simulate_block,
}

"""YuriArm 命令行入口。

用法（在 YuriArm 目录下）：
    python -m yuriarm --mock                      # 交互式控制台（仿真后端，离线可玩）
    python -m yuriarm --mock status
    python -m yuriarm --mock teach pick_low       # 记录当前关节角为命名姿态
    python -m yuriarm --mock pose home
    python -m yuriarm --mock pick                 # 执行示教-回放拾取周期
    python -m yuriarm serve --port 8765           # 启动 TCP 指令服务器
    python tools/send_command.py --cmd telemetry  # 向服务器发指令
    python -m yuriarm run --target red --target blue   # 完整抓取任务（需感知/手动 blocks）

真机模式（默认，lerobot 环境）：
    python -m yuriarm connect
    python -m yuriarm calibrate                   # 首次上机交互式标定
    python -m yuriarm --auto-connect move --shoulder_lift=30 --duration 2
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from .arm import YuriArm
from .commands import CommandContext, dispatch
from .config import load_config
from .perception import Perception
from .planner import Block, PickPlanner
from .protocol import Command

# 让 `python yuriarm/__main__.py` 也能运行
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None, help="配置文件路径（默认 YuriArm/configs/arm.json）")
    parser.add_argument("--mock", action="store_true", help="使用仿真后端（无需硬件/COM 口）")
    parser.add_argument("--auto-connect", action="store_true", help="命令前自动 connect（真机慎用）")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="yuriarm", description="YuriArm 机械臂指令控制")
    _add_common(ap)
    sub = ap.add_subparsers(dest="subcommand")

    sub.add_parser("status", help="查看状态")
    sub.add_parser("connect", help="连接机械臂")
    sub.add_parser("disconnect", help="断开连接")
    sub.add_parser("calibrate", help="交互式标定（真机，需控制台）")
    sub.add_parser("home", help="回到 home 姿态")
    sub.add_parser("estop", help="急停（关力矩）")
    sub.add_parser("resume", help="解除急停")
    sub.add_parser("telemetry", help="读取遥测")

    p = sub.add_parser("move", help="移动到关节角，如 move --shoulder_lift=30 --elbow_flex=-20")
    for _m in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"):
        p.add_argument(f"--{_m}", type=float, default=None, dest=_m)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--max-velocity", type=float, default=None)

    p = sub.add_parser("pose", help="移动到命名姿态，如 pose home")
    p.add_argument("name", nargs="?", default=None)
    p.add_argument("--max-velocity", type=float, default=None)

    p = sub.add_parser("teach", help="记录当前关节角为姿态，如 teach pick_low")
    p.add_argument("name")

    p = sub.add_parser("gripper", help="gripper open|close")
    p.add_argument("action", choices=["open", "close"])
    p.add_argument("--max-load", type=float, default=None)
    p.add_argument("--timeout", type=float, default=None)
    p.add_argument("--velocity", type=float, default=None)

    p = sub.add_parser("pick", help="执行示教-回放拾取周期")
    p.add_argument("--pick-high", default=None)
    p.add_argument("--pick-low", default=None)
    p.add_argument("--drop", default=None)
    p.add_argument("--max-velocity", type=float, default=None)

    p = sub.add_parser("scan", help="扫描桌面方块（需感知）")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("run", help="完整抓取任务（感知或手动 blocks）")
    p.add_argument("--target", action="append", default=None, help="目标色（可多次）")
    p.add_argument("--blocks-json", default=None, help="手动方块列表 JSON")
    p.add_argument("--block", action="append", default=None,
                   help="手动方块 color@x,y（可多次，如 red@10,20）")

    p = sub.add_parser("serve", help="启动 TCP 指令服务器")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)

    p = sub.add_parser("send", help="向运行中的服务器发一条指令（等同 tools/send_command.py）")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--cmd", default=None, help="指令名，如 move_joints")
    p.add_argument("--params", default=None, help='JSON 参数，如 \'{"targets":{"shoulder_lift":30}}\'')
    p.add_argument("--raw", default=None, help="原始指令 JSON（优先于 --cmd/--params）")

    sub.add_parser("bench", help="台上单臂夹取冒烟测试（tools/bench_pick.py）")

    p = sub.add_parser("simulate-block", help="[mock] 模拟夹爪间有无方块（调试）")
    p.add_argument("--present", action="store_true", default=True)
    p.add_argument("--absent", action="store_true")
    return ap


def _parse_move_targets(args) -> dict[str, float]:
    targets: dict[str, float] = {}
    for key, val in vars(args).items():
        if key.startswith("shoulder_") or key.startswith("elbow_") or key.startswith("wrist_") or key == "gripper":
            if val is not None:
                targets[key] = float(val)
    if not targets:
        raise SystemExit("move 需要至少一个关节参数，如 --shoulder_lift=30")
    return targets


def _make_context(args) -> CommandContext:
    cfg = load_config(args.config)
    arm = YuriArm(cfg, mock=args.mock)
    ctx = CommandContext(arm=arm, config=cfg, perception=Perception(cfg), planner=PickPlanner(cfg))
    if args.mock or args.auto_connect:
        arm.connect()
    return ctx


def _run_command(ctx: CommandContext, cmd: Command) -> dict[str, Any]:
    result = dispatch(ctx, cmd)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return result.to_dict()


def _cmd_from_cli_args(args) -> Command:
    """把 CLI 子命令参数转成 protocol.Command（REPL/服务器/单条命令共用同一协议）。"""
    sub = args.subcommand
    params: dict[str, Any] = {}
    if sub == "move":
        params = {"targets": _parse_move_targets(args)}
        if args.duration is not None:
            params["duration"] = args.duration
        if args.max_velocity is not None:
            params["max_velocity"] = args.max_velocity
    elif sub == "pose":
        if not args.name:
            raise SystemExit("pose 需要姿态名（可用: home/pick_high/pick_low/drop）")
        params["pose"] = args.name
        if args.max_velocity is not None:
            params["max_velocity"] = args.max_velocity
    elif sub == "teach":
        params["name"] = args.name
    elif sub == "gripper":
        if args.action == "open":
            if args.velocity is not None:
                params["velocity"] = args.velocity
        else:
            if args.max_load is not None:
                params["max_load"] = args.max_load
            if args.timeout is not None:
                params["timeout"] = args.timeout
    elif sub == "pick":
        for k in ("pick_high", "pick_low", "drop"):
            v = getattr(args, k, None)
            if v:
                params[k] = v
        if args.max_velocity is not None:
            params["max_velocity"] = args.max_velocity
    elif sub == "scan":
        pass
    elif sub == "run":
        if args.target:
            params["target_colors"] = args.target
        if getattr(args, "block", None):
            params["blocks"] = []
            for spec in args.block:
                color, _, xy = spec.partition("@")
                if not color or not xy:
                    raise SystemExit(f"--block 格式应为 color@x,y，收到: {spec}")
                x, y = xy.split(",")
                params["blocks"].append({"color": color, "x_mm": float(x), "y_mm": float(y)})
        elif getattr(args, "blocks_json", None):
            params["blocks"] = json.loads(args.blocks_json)
    elif sub == "simulate-block":
        params["present"] = not args.absent
    # CLI 子命令名 -> 协议指令名映射（teach/pose/gripper 等与协议名不同）
    if sub == "gripper":
        cmd_name = "open_gripper" if args.action == "open" else "close_gripper"
    else:
        cmd_name = {"move": "move_joints", "pose": "move_to_pose", "teach": "record_pose",
                    "simulate-block": "simulate_block"}.get(sub, sub)
    return Command(cmd=cmd_name, params=params)


def run_repl(ctx: CommandContext, parser: argparse.ArgumentParser) -> None:
    """交互式控制台：输入命令直接执行（协议与服务器一致）。"""
    print("YuriArm 交互控制台（Ctrl+C 退出并急停）")
    print("可用指令:", ", ".join(sorted(
        ["status", "connect", "disconnect", "calibrate", "move", "pose", "teach",
         "gripper open|close", "pick", "home", "estop", "resume", "telemetry",
         "scan", "run", "serve", "send", "bench", "simulate-block"])))
    while True:
        try:
            line = input("yuriarm> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[exit] 触发急停并退出")
            try:
                ctx.arm.estop()
            except Exception:
                pass
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        try:
            tokens = shlex.split(line)
            sub_argv = [a for a in tokens]
            sub_args = parser.parse_args(sub_argv)
            if sub_args.subcommand is None:
                print("未知指令")
                continue
            if sub_args.subcommand in ("serve", "send", "bench"):
                # 子进程式功能在 REPL 中直接提示
                print(f"[REPL] '{sub_args.subcommand}' 请退出后在命令行执行: python -m yuriarm {line}")
                continue
            cmd = _cmd_from_cli_args(sub_args)
            _run_command(ctx, cmd)
        except SystemExit:
            continue
        except KeyboardInterrupt:
            print("\n[Ctrl+C] 急停")
            try:
                ctx.arm.estop()
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            print(f"[错误] {type(e).__name__}: {e}")


def _run_serve(ctx: CommandContext, args) -> None:
    from .server import YuriArmServer
    host = args.host or ctx.config.server["host"]
    port = int(args.port or ctx.config.server["port"])
    ctx.server_mode = True
    srv = YuriArmServer(ctx, host=host, port=port)
    srv.start()
    print(f"服务器运行中: {host}:{port}（Ctrl+C 停止）")
    try:
        import time
        while srv.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[stop] 停止服务器")
    finally:
        srv.stop()


def _run_send(args) -> None:
    from .config import load_config as _lc
    import socket

    cfg = _lc(args.config)
    host = args.host or cfg.server["host"]
    port = int(args.port or cfg.server["port"])
    if args.raw:
        raw = args.raw
    else:
        if not args.cmd:
            raise SystemExit("send 需要 --raw 或 --cmd")
        params = json.loads(args.params) if args.params else {}
        raw = json.dumps({"cmd": args.cmd, "params": params})
    with socket.create_connection((host, port), timeout=5.0) as sock:
        sock.sendall((raw + "\n").encode("utf-8"))
        data = sock.recv(65536).decode("utf-8", errors="replace")
    try:
        parsed = json.loads(data)
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(data)


def _run_bench(args) -> int:
    # tools 是 YuriArm 根下的独立包，与 yuriarm 包平级
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from tools.bench_pick import main as bench_main
    return bench_main(argv=["--config", args.config or "", "--mock" if args.mock else ""])


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "send":
        _run_send(args)
        return 0

    ctx = _make_context(args)
    if args.subcommand == "run" and args.blocks_json:
        ctx.manual_blocks = [Block(**b) for b in json.loads(args.blocks_json)]
    try:
        if args.subcommand is None:
            run_repl(ctx, parser)
            return 0
        if args.subcommand == "serve":
            _run_serve(ctx, args)
            return 0
        if args.subcommand == "bench":
            return _run_bench(args)
        cmd = _cmd_from_cli_args(args)
        _run_command(ctx, cmd)
        return 0
    except KeyboardInterrupt:
        print("\n[Ctrl+C] 触发急停")
        try:
            ctx.arm.estop()
        except Exception:
            pass
        return 130


if __name__ == "__main__":
    sys.exit(main())

# YuriArm：机械臂指令控制与方块抓取

> 通过电脑直接发送指令控制 SO-101 机械臂抓取方块；摄像头 + ML 自动识别（YuriEye）作为
> 后续接入的感知层，当前已完成命令驱动核心（M0），感知/运动学为可插拔接口。
> 详细设计见 [docs/方案设计.md](docs/方案设计.md)。

> 合作者任务：主动臂接电脑并远程控制从动臂，见
> [docs/ARM_TELEOP_TASK.md](docs/ARM_TELEOP_TASK.md)。

## 当前能力（2026-08-31，v0.1）

| 模块 | 状态 | 说明 |
|---|---|---|
| 指令协议 `protocol.py` | ✅ | JSON 指令/结果报文，控制台、TCP 服务器、未来 ESP32 固件共用 |
| 机械臂驱动 `arm.py` | ✅ | 真机 `LerobotArm`（lerobot SO101Follower）+ 仿真 `MockArm`；安全门面：限速/限位/忙锁/急停 |
| 夹取原语 | ✅ | `close_gripper` 用 Present_Load 跳变判夹住；`pick` 完整示教-回放拾取周期 |
| 指令入口 `cli.py` | ✅ | 交互式控制台 / 单条命令 / TCP 指令服务器（`serve`）/ `send` |
| 抓取规划 `planner.py` | ✅ | 任务空间路径（高空过、垂直落）、按价值/紧贴/风险排序、可达性接口 |
| 状态机 `state_machine.py` | ✅ | SCAN→PLAN→EXECUTE→VERIFY，单颗容错 + 结构化报告 |
| 感知 `perception.py` | 🔜 接入缝 | 封装 YuriEye（像素→mm 单应）；缺失时优雅降级手动模式 |
| 无线执行端（ESP32-S3） | ⏳ M3.5 | 协议已定（firmware/protocol.md），固件待硬件到位后实现 |
| SO-101 FK/IK | ⏳ M1 | `planner.Kinematics` 接口已留，真机标定后实现 |

## 环境

真机模式需要 `lerobot` conda 环境（与父仓库共用，Python 3.10 + scservo_sdk）：

```powershell
& E:\Anaconda\envs\lerobot\python.exe -m unittest discover -s YuriArm\tests   # 跑测试
```

## 快速开始（离线，`--mock` 仿真后端，无需硬件）

```powershell
cd YuriArm

# 1) 交互式控制台（仿真）
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock
#   move --gripper=100          # 张开夹爪
#   teach pick_high             # 记录当前位形为 pick_high
#   move --shoulder_lift=-20 --elbow_flex=20
#   teach pick_low              # 记录下压位形（夹爪保持张开）
#   move --shoulder_pan=40
#   teach drop                  # 记录投放位形
#   simulate-block --present    # [mock] 模拟夹爪间有方块
#   run --target red --block red@10,10   # 完整抓取任务
#   exit

# 2) 单条命令（每次独立进程，位置从零开始，适合测试协议）
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock status
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock move --shoulder_lift=30 --duration 0.3
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock telemetry

# 3) 冒烟测试（M0）：连接→拾取→断开
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock bench
```

## 真机模式（SO-101 follower，默认 COM7）

```powershell
cd YuriArm
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm connect      # 需标定文件存在
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm calibrate    # 首次：交互式标定（按提示操作）
# 交互式示教姿态（真机）：进入控制台后
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm
#   connect
#   手动把臂摆到目标正上方（夹爪张开）→ teach pick_high
#   手动下压到手指套住方块的位置（夹爪张开）→ teach pick_low
#   手动移到料篮上方 → teach drop
#   pick                          # 执行拾取周期
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm bench         # 台上夹取冒烟测试
```

> ⚠️ `pick_high` / `pick_low` 必须**夹爪张开**时示教（夹取动作由 `close_gripper` 用负载判定完成）。
> 夹爪开/合方向取决于装配与标定，第一次上机先 `gripper open` / `gripper close` 校核，
> 方向不对就交换 `configs/arm.json` 里 `gripper.open` / `gripper.close` 的值。

## 通过 TCP 指令服务器"直接发送指令"

```powershell
# 终端 1：启动服务器（默认 127.0.0.1:8765，仅本机）
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock serve --port 8765

# 终端 2：发送指令
& E:\Anaconda\envs\lerobot\python.exe tools\send_command.py --port 8765 --cmd ping
& E:\Anaconda\envs\lerobot\python.exe tools\send_command.py --port 8765 --cmd move_joints --params '{"targets":{"shoulder_lift":30},"duration":2}'
& E:\Anaconda\envs\lerobot\python.exe tools\send_command.py --port 8765 --cmd telemetry
& E:\Anaconda\envs\lerobot\python.exe tools\send_command.py --port 8765 --cmd estop
```

任何程序（Python/脚本/GUI/未来 ML 管线）都可以连 127.0.0.1:8765 发 JSON：

```jsonc
{"id": 1, "cmd": "move_joints", "params": {"targets": {"shoulder_lift": 30.0}, "duration": 2.0}}
{"id": 2, "cmd": "pick",        "params": {}}
{"id": 3, "cmd": "estop",       "params": {}}
```

指令全集见 `yuriarm/protocol.py` 的 `KNOWN_COMMANDS`（固件版规范见 `firmware/protocol.md`）。

## 配置

`configs/arm.json`（首次运行自动生成，含默认值）：

- `arm`：COM 口 / 机器人 id（标定文件名） / 是否用角度制
- `safety`：限速、插值频率、急停负载阈值、关节限位
- `gripper`：开/合目标值、合拢步进/轮询、夹住负载阈值、超时
- `pick`：拾取使用的姿态名、任务空间参数（M1+）
- `blocks`：方块尺寸、目标色、分值、投放区、最小缝隙
- `poses`：命名姿态（`teach` 写入）
- `server`：指令服务器监听地址
- `perception`：YuriEye 相机/单应/权重路径（M1+）

## 测试

```powershell
& E:\Anaconda\envs\lerobot\python.exe -m unittest discover -s YuriArm\tests -v
```

覆盖：协议编解码、Mock 后端运动/限位/急停/夹取判定/拾取周期、规划排序/路径、
状态机（成功/失败/目标过滤/手动模式）、单应变换与验证、TCP 服务器指令。

## 目录结构

```
YuriArm/
├── docs/方案设计.md        设计文档（v0.3 + 实现状态）
├── firmware/protocol.md    ESP32-S3 无线执行端协议规范（M3.5 待实现）
├── yuriarm/
│   ├── config.py           配置（默认值 + 用户 JSON + 姿态持久化）
│   ├── protocol.py         指令/结果协议（传输无关）
│   ├── arm.py              后端抽象 + 真机/仿真 + 安全门面
│   ├── planner.py          任务空间规划 + 排序 + 可达性接口
│   ├── perception.py       YuriEye 封装（单应/检测/验证，优雅降级）
│   ├── state_machine.py    抓取任务状态机
│   ├── commands.py         指令分发（CLI/REPL/服务器共用）
│   ├── server.py           TCP JSON 指令服务器
│   └── cli.py / __main__.py
├── tools/
│   ├── bench_pick.py       M0 台上单臂夹取冒烟测试
│   ├── send_command.py     向指令服务器发指令
│   └── calib_homography.py 俯视→桌面单应标定（棋盘格/点对）
└── tests/                  unittest（无硬件可跑）
```

## 兼容性与约束说明

- **不改父仓库任何文件**：只通过 lerobot 公共接口（SO101Follower / FeetechMotorsBus）驱动真机；
  lerobot 仅在真机路径惰性导入，纯逻辑模块在任意 Python 中可导入。
- **COM 口独占**：同一时刻只能有一个进程占用机械臂 COM 口（lerobot_teleoperate 与本工具互斥，
  这是串口物理约束，不是代码冲突）。
- **感知/运动学降级**：没有相机/标定也能用（手动 blocks + 示教-回放）；接入后逐段替换，不重写主流程。
- **安全**：限速/限位/急停/夹取负载判定/忙锁；服务器默认只监听 127.0.0.1。

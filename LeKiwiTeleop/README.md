# LeKiwiTeleop — SO-101 主动臂带动从动臂（遥操作参考）

> 独立参考配置，与本仓库 YuriArm/YuriEye 的 ESP32 无线方案无关。
> 本目录是 **LeRobot 有线版（笔记本直连两块臂）** 的配置与使用说明。

## 概述

```text
主动臂(leader, so101) —— USB ——> 笔记本(跑 LeRobot 0.6.1) <—— USB —— 从动臂(follower, so101)
轮子：用 YuriChassis/ 的独立代码控制，不经 LeRobot。
```

- 主动臂 = 你手握控制的那台（只读角度）
- 从动臂 = 跟随动作、执行抓取的那台（自己出力）
- 轮子 = 独立于机械臂，用 YuriChassis/kiwi_drive.py 单独控制

## 环境

```text
Python 3.12 venv + lerobot 0.6.1（本机示例：C:\Users\21209\lerobot_venv312）
源码：github.com/huggingface/lerobot (tag v0.6.1)
端口示例：主动臂 COM7 | 从动臂 COM4（以实际为准）
```

> 本机注意：学校网络 TLS 劫持会让 `uv`/`curl` 装包失败（证书是 njmu.edu.cn）。
> 用 venv 自带 `pip`（走 Windows 系统证书）可绕过。

## 硬件接线

```text
笔记本
 ├── USB口A → 主动臂控制板 (例 COM7)
 └── USB口B → 从动臂控制板 (例 COM4)
两块臂各自独立 USB = 两条独立总线，舵机 ID 各自 1~6，互不冲突。
轮子走 YuriChassis 那块板，与这里无关。
```

先确认端口在线：

```bash
C:\Users\21209\lerobot_venv312\Scripts\python.exe -c "import serial.tools.list_ports as lp; [print(p.device,p.description) for p in lp.comports()]"
```

## 校准（每台臂首次 / 跟动异常时重做）

从动臂（so101_follower）：
```bat
C:\Users\21209\lerobot_venv312\Scripts\lerobot-calibrate.exe --robot.type=so101_follower --robot.port=COM4
```

主动臂（so101_leader，注意是 --teleop 不是 --robot）：
```bat
C:\Users\21209\lerobot_venv312\Scripts\lerobot-calibrate.exe --teleop.type=so101_leader --teleop.port=COM7
```

> 校准交互步骤（需人在场）：
> 1. 把臂摆到活动范围中间 → Enter
> 2. 出现 MIN/POS/MAX 表格 → 依次用手把每个关节从头转到尾（shoulder_pan→shoulder_lift→elbow_flex→wrist_flex→gripper），看 MIN/MAX 变化
> 3. 全动过 → Enter → 显示 "Calibration saved" 完成

若要从头重校：删掉校准文件再跑：
```text
%USERPROFILE%\.cache\huggingface\lerobot\calibration\robots\so_follower\*.json
%USERPROFILE%\.cache\huggingface\lerobot\calibration\teleoperators\so_leader\*.json
```

## 遥操作（主动臂带从动臂）

方式A：双击 `teleop_so101_start.bat`
方式B：命令行
```bat
C:\Users\21209\lerobot_venv312\Scripts\lerobot-teleoperate.exe --robot.type=so101_follower --robot.port=COM4 --teleop.type=so101_leader --teleop.port=COM7
```
方式C：直接跑本项目源码（封装了官方 API，不再经 CLI）
```bat
C:\Users\21209\lerobot_venv312\Scripts\python.exe teleop_so101.py
```
> 源码里改 `LEADER_PORT` / `FOLLOWER_PORT` / `FPS` 三个常量即可。

运行后握主动臂动 → 从动臂跟着动。停止按 Ctrl+C。

## 文件清单

| 文件 | 用途 |
|---|---|
| `teleop_so101.py` | **遥操作源码**：自研封装 lerobot Python API，主动臂读角度→从动臂写角度 |
| `teleop_so101_start.bat` | 一键启动（调用官方 CLI，需改端口为实际值） |
| `SO101_遥操作操作说明.md` | 完整操作与排障文档 |

## 端口参数速查

| 端 | 参数 | 值 |
|---|---|---|
| 从动臂 | `--robot.type` / `--robot.port` | `so101_follower` / COM4 |
| 主动臂 | `--teleop.type` / `--teleop.port` | `so101_leader` / COM7 |

## 常见问题

| 现象 | 解决 |
|---|---|
| 端口被占用 PermissionError | 关掉占用串口的程序（PyCharm/FD/残留 python） |
| 找不到舵机 / found 空 | 检查舵机供电、接线、波特率(应 1000000) |
| Mismatch calibration | 重跑该校准 |
| 跟动方向反/幅度不对 | 重新校准对应臂 |

# 交接文档 — 给 Codex（2026-09-04）

> 本会话从 Hermes 交接给 Codex 继续 Yuri 项目。先读本文件 + `SOUL.md` + `README.md`，
> 再动任何代码。仓库工作目录：`C:\Users\21209\Desktop\Yuri`（git main，私有
> `Shihou-Matsuri/Yuri`，账号 s0lo201，已配置好凭据）。

## 0. 一句话现状

机械臂遥操作（teleop_joints 直写）✅ 真机验证通过；轮子 WiFi 键盘遥控 ✅ 通过；
**dual_remote（同时控制）✅ 真机实测通过（2026-09-04 修复 stop/E/exit 三个 bug），首要任务完成。**

## 1. 架构（三句话）

- 笔记本（读主动臂 COM7 / 键盘）→ 一条 ESP32 连接（WiFi TCP 192.168.4.1:8765 或
  USB 串口 COM8 @115200）→ ESP32 分两条舵机总线：UART1→从动臂 6×STS3215，
  UART2→小车 3 舵机（ID 7/8/9）。
- 遥操作用 **teleop_joints 直写**：PC 每帧发 6 关节归一化目标，ESP32 直接写
  Goal_Position，无插值状态机、无读回、无回包。舵机内部平滑。
- **高频指令一律不回包**：heartbeat / car_drive / move_joints / teleop_joints。
  回包会堆积淹没 ping → 客户端误判断连重连（真实现场翻车过）。

## 2. 代码地图

| 文件 | 作用 |
|---|---|
| `SOUL.md` | 设计决策 + 血泪教训（**必读**） |
| `YuriArm/yuriarm/leader_bridge.py` | LeaderBridge：读 leader → 映射/死区 → 发指令（cmd_name 可配，默认 teleop_joints） |
| `YuriArm/tools/leader_remote.py` | 机械臂单控 CLI（--link serial/tcp，含单实例 pid 锁） |
| `YuriChassis/car_remote.py` | 轮子单控 CLI（TcpTransport 带 ping 自动重连；SerialTransport） |
| `YuriChassis/dual_remote.py` | **同时控制**：单循环 20Hz = bridge.step(机械臂) + msvcrt 键盘(轮子) + heartbeat；`_JsonTransport` 适配 dict/bytes |
| `YuriChassis/kiwi_drive.py` | 三轮 kiwi 运动学 + 键位（KEY_MOTIONS / MOTION_VECTORS / build_speeds 在 car_remote） |
| `YuriArm/firmware/esp32s3_exec/` | 固件：esp32s3_exec.ino（主循环/回包抑制）、protocol.cpp（teleop_joints 分支）、motion.cpp/h（writeTeleopTargets + teleopActive）、config.h（gripper range、estop_load） |
| `YuriArm/firmware/protocol.md` | 协议规范（含 teleop_joints 语义） |

## 3. 首要任务：dual_remote 真机实测

**✅ 已完成（2026-09-04）**：真机实测通过。本轮修复三个 bug——空格停不住（只发 heartbeat 不刹停）、
Q 退出车不停（收尾未等 ESP32 处理就 close）、E 使臂失效（全局 estop 无显式恢复）。详见 git log / SOUL.md。
历史预期行为：手握主动臂 → 从动臂跟随；同时 W/S/A/D/Z/X 键盘 → 轮子转。
已知修复：transport 层 dict/bytes 适配（提交 015cd7b），import 链路验证过。

实测命令（用户自己 cmd 终端跑，键盘程序必须命令行跑，PyCharm 抓不到键）：
```bat
cd C:\Users\21209\Desktop\Yuri\YuriChassis
C:\Users\21209\Desktop\Yuri\lerobot_venv312\Scripts\python.exe dual_remote.py   :: 默认 WiFi TCP
:: 或 --serial COM8 走 USB
```
前置：电脑 WiFi 连 `YuriArm-AP`（密码 yuriarm123，会断外网）；车体抬空；
从动臂+小车供电；无其它进程占 COM7/COM8。若 TCP 超时 = ESP32 旧连接没释放 →
按 RESET 重启 ESP32（USB 复位也行：打开 COM8 时 DTR/RTS 自动复位）。

## 4. 环境事实（本机）

- Python：`C:\Users\21209\Desktop\Yuri\lerobot_venv312\Scripts\python.exe`（py3.12 + lerobot 0.6.1 +
  pyserial）。**venv 的 python.exe 是 venvlauncher**——曾 0 字节损坏报"此应用不可运行"，
  修复 = 从 uv python 目录复制 venvlauncher.exe 改名（不是完整 python.exe）。
- 串口：主动臂 COM7（CH343）；ESP32 COM8（指令口 115200）。从动臂由 ESP32 UART1 驱动。
- 烧录：`arduino-cli upload -p COM8 --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc`（需用户 BOOT+RESET）；
  `~/.arduino-cli/arduino-cli.exe`。编译在 `YuriArm/firmware/esp32s3_exec/` 下。
- 学校网络 TLS MITM：pip 走系统证书可用，uv/rustls 失败。

## 5. 硬性约束（用户强制）

- 只用简体中文回复；术语保留英文（teleop_joints、watchdog）；惜字如金；禁吹捧；不确定就说不确定。
- 写码前执行：全局兼容（同运行时共存）、禁硬编码/临时逻辑、列技术债、标回归风险、
  拒绝"只在单一场景能跑"的代码、积极更新文档。
- git：s0lo201 身份；标题 ≤50 字符祈使句；正文写 what/why。
- 真机动作（烧录、驱动舵机）前先跟用户确认；用户在场配合时测试时机要喊清楚开始/结束。

## 6. 已知坑（SOUL.md 有完整版）

- 同一串口只允许一个控制进程（单实例 pid 锁在 leader_remote，dual_remote 暂无——
  若加注意别和 leader_remote 的锁冲突）。
- 重开 COM8 会复位 ESP32（读到 boot 日志 ≠ 崩溃）。
- 从动臂/主动臂供电接触不良史：只读到部分舵机 ID / 读数恒 0 / gripper 恒 2048
  → 先查供电再查代码。
- gripper 机械 range = raw [2045, 3479]（config.h 已改，勿改回）。
- estop_load=2000；watchdog 500ms 覆盖 interpActive + teleopActive。
- 测试时机要对齐：让用户"大幅转"时必须明确喊开始/结束，读数恒定可能是用户没转。
- 大幅动作"卡住"先查 status 的 estop/watchdog_ok，再查负载，别直接猜参数。

## 7. 后续方向（未定优先级）

- ✅ dual_remote 实测已通过（2026-09-04，修复后已提交）
- 📐 综合遥控台需求与 GUI 风格已定稿（`docs/REMOTE_CONSOLE_REQ.md`，U1；U2 实现待排期）
- YuriEye 视觉识别与机械臂集成（抓取闭环，另一台电脑做过，本机未接）
- 底盘落地实测（当前只抬空验证方向）
- 可选：dual_remote 加单实例锁防多开

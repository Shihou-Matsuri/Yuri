# Yuri

机械臂 + 小车 + 摄像头协同的模块化机器人（基于 ESP32-S3 无线执行端）。

> **动手前先读 [SOUL.md](SOUL.md)** —— 核心架构决策与血泪教训（遥操作直写、
> 高频指令不回包、单实例锁、真机联调铁律）。

## 仓库结构

| 目录 | 说明 |
|---|---|
| `YuriArm/` | SO-101 机械臂：ESP32-S3 固件（`firmware/esp32s3_exec/`）+ 遥操作桥（`yuriarm/`+`tools/leader_remote.py`） |
| `YuriChassis/` | 三轮 kiwi 底盘：运动学 + WiFi 键盘遥控（`car_remote.py` / `dual_remote.py` 臂+轮同控） |
| `YuriEye/` | 彩色立方体识别（YOLOv8 + 相机标定），感知层 |
| `LeKiwiTeleop/` | LeKiwi 有线主从遥操作参考（独立文档，非本架构） |
| `SOUL.md` | **设计灵魂与教训，先读** |

## 当前状态（2026-09-04）

| 模块 | 状态 |
|---|---|
| ESP32-S3 无线执行端（WiFi AP + USB，6×STS3215） | ✅ 真机验证 |
| **主动臂 → 从动臂遥操作（teleop_joints 直写）** | ✅ 真机验证：小幅/大幅/多关节跟手，不卡死 |
| 小车 WiFi 键盘遥控（car_drive 电机恒速） | ✅ 真机验证（含自动重连） |
| **机械臂 + 小车同时控制（dual_remote）** | ✅ 真机验证：臂跟手 + 轮键盘同跑；空格停 / E 轮子急停 / Q 刹停退出 |
| BLE 通道 | 🔇 已禁用（用户决策：只留 WiFi） |
| YuriEye 视觉识别 | 🔜 待与机械臂集成 |

## 架构

```
笔记本（感知/规划/遥操作桥）
        │ WiFi AP 192.168.4.1:8765 / USB 串口 115200
        ▼
   ESP32-S3（无线执行端：直写 / 看门狗 500ms / 本地急停）
        │
        ├── UART1 ＋ Waveshare Adapter(A) ──► 从动臂 6×STS3215
        └── UART2 ＋ Waveshare Adapter(A) ──► 小车 3 舵机（ID 7/8/9）
```

## 快速开始

### 主动臂 → 从动臂遥操作（本机 USB 方式）

```powershell
cd YuriArm
C:\Users\21209\lerobot_venv312\Scripts\python.exe tools\leader_remote.py --link serial --serial COM8
```

- 前置：主动臂 COM7、ESP32 COM8、从动臂供电；小车不得同时运行。
- WiFi 方式：电脑连 `YuriArm-AP`（密码 yuriarm123），`--link tcp`。
- 停止：Ctrl+C（自动 estop）。更多见 `YuriArm/README.md`。

### 小车 WiFi 键盘遥控

```powershell
cd YuriChassis
C:\Users\21209\lerobot_venv312\Scripts\python.exe car_remote.py
```

W/S 前后 · A/D 横移 · Z/X 旋转 · 空格停 · E 急停 · Q 退出（车体抬空首测）。

### 机械臂 + 小车同时控制（dual_remote）

```powershell
cd YuriChassis
C:\Users\21209\lerobot_venv312\Scripts\python.exe dual_remote.py
```

- 前置：主动臂 COM7 + ESP32（默认 WiFi TCP，或 `--serial COM8`）；从动臂 + 小车供电；车体抬空首测。
- 操作：手握主动臂 → 从动臂跟随；W/S/A/D/Z/X 轮子 · 空格停 · E 轮子急停（不动臂）· Q 退出（刹停+estop）。
- 键盘程序必须命令行跑（PyCharm 抓不到键）。

### 烧录固件

```powershell
cd YuriArm/firmware/esp32s3_exec
$HOME/.arduino-cli/arduino-cli.exe upload -p COM8 --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc .
# 需手动 BOOT+RESET；指令口波特率 115200
```

## 设计约束（维护者请遵守）

- 只通过 lerobot 公共接口驱动真机，不改动父仓库代码。
- **遥操作用 `teleop_joints` 直写**；`move_joints` 仅用于脚本化单次移动。
- **高频指令（heartbeat/car_drive/move_joints/teleop_joints）不回包**；
  需要状态用 status/telemetry 轮询。
- 新增/修改必须与现有模块在**同一运行上下文**兼容；固件 `protocol.cpp` 与
  `firmware/protocol.md`、PC 侧命令表必须同步。
- 每处改动列出技术债与回归风险，并同步更新 README / protocol.md / SOUL.md。

## 相关文档

- `SOUL.md`：设计灵魂与教训（先读）
- `YuriArm/docs/方案设计.md`：YuriArm 设计
- `YuriArm/firmware/protocol.md`：ESP32 JSON 协议（含 teleop_joints）
- `YuriArm/docs/ARM_TELEOP_TASK.md`：主动臂遥控从动臂交接任务
- `docs/ESP32_CAR_TASK.md`：ESP32 遥控小车任务
- `docs/ROADMAP.md`：总体路线

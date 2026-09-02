# Yuri

机械臂 + 小车 + 摄像头协同的模块化机器人（基于 ESP32-S3 无线执行端）。

## 仓库结构

| 目录 | 说明 |
|---|---|
| `YuriArm/` | SO-101 机械臂指令控制、抓取规划、ESP32-S3 无线执行端固件（已完成并真机验证） |
| `YuriEye/` | 彩色立方体识别（YOLOv8 + 相机标定），作为感知层接入 |

## 当前状态（2026-09-02）

| 模块 | 状态 |
|---|---|
| YuriArm 指令协议 / 机械臂驱动 / 夹取 / 规划 / 状态机 | ✅ 完成，`--mock` 可无硬件跑测试 |
| ESP32-S3 无线执行端（WiFi AP / USB / BLE 三通道，6×STS3215） | ✅ 真机验证（F1/F2） |
| YuriEye 视觉识别 | ✅ YOLO 模型已训练（mAP50 0.949），待与 YuriArm 集成 |
| ESP32 遥控小车 | ⏳ 下一任务，详见 `docs/ESP32_CAR_TASK.md` |
| 机械臂 + 轮子 + 摄像头协同 | 🔜 远期目标 |

## 架构

```
笔记本（感知/规划/指令）
        │ WiFi AP 192.168.4.1:8765 / BLE YuriArm-S3
        ▼
   ESP32-S3（无线执行端：插值 / 看门狗 / 本地急停）
        │
        ├── UART1 ＋ Waveshare Adapter(A) ──► 主臂 6×STS3215（已验证）
        └── UART2 ＋ Waveshare Adapter(A) ──► 小车 3 舵机（待接，见任务文档）
```

## 快速开始

### YuriArm（机械臂，仿真后端无硬件）

```powershell
cd YuriArm
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock status
& E:\Anaconda\envs\lerobot\python.exe -m yuriarm --mock move --shoulder_lift=30 --duration 0.3
```

> 真机/标定/抓取详细用法见 `YuriArm/README.md`。

### ESP32 无线执行端

```powershell
# 串口/蓝牙驱动工具在 YuriArm/tools/ 下
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --status
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_smoke.py --serial COM19 --diag
```

固件说明见 `YuriArm/firmware/esp32s3_exec/README.md` 与 `YuriArm/firmware/protocol.md`。

### YuriEye（视觉）

```powershell
cd YuriEye
# 需自行训练/获取权重（data/、runs/、weights/ 不入库，避免仓库过大）
& E:\Anaconda\envs\lerobot\python.exe tools\live_detect.py
```

## 设计约束（维护者请遵守）

- 只通过 lerobot 公共接口驱动真机，不改动父仓库代码。
- 新增/修改必须与现有模块在**同一运行上下文**兼容；不得写死临时逻辑、破坏协议接口契约。
- 改动前先做全局兼容性检查；如与 `protocol.py` / 固件 `protocol.cpp` 不一致，须同步。
- 每处改动列出技术债与回归风险，并同步更新本文档与对应 README。

## 相关文档

- `YuriArm/docs/方案设计.md`：YuriArm 设计
- `YuriArm/firmware/protocol.md`：ESP32 JSON 协议
- `YuriEye/docs/方案设计.md`：YuriEye 设计
- `docs/ROADMAP.md`：总体路线
- `docs/ESP32_CAR_TASK.md`：ESP32 遥控小车任务（给协作方）

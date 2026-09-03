# YuriChassis — LeKiwi 三轮全向底盘（PC 直控版）

三轮 kiwi 全向底盘，3×STS3215 舵机(12V, 电机恒速模式)，USB→舵机控制板直连 PC。

> 若你用的是 **ESP32-S3 无线**版，见仓库根 README / YuriArm 的 firmware（本目录是 PC USB 直控）。

## 文件清单

| 文件 | 用途 |
|---|---|
| `feetech.py` | 飞特 STS 总线协议（含 `encode_motor_speed`：**BIT15=方向 + 低15位幅值**，不是补码） |
| `kiwi_drive.py` | 主程序：三轮全向运动学 + WASD 键盘控制。ID7 左前/ID8 后/ID9 右前 |
| `car_remote.py` | WiFi TCP 键盘遥控入口 |
| `car_remote_ble.py` | BLE 键盘遥控入口 |
| `scan_ids.py` | 扫描总线在线舵机 ID |
| `calibrate_direction.py` | 单轮正转测物理转向 |
| `single_wheel_calib.py` | 单轮标定：看整车滑向反解驱动方位 |
| `autocalib.py` | 自动标定：看车滑向自动写回 kiwi_drive.py 的 WHEEL_ANGLES_DEG |
| `diag_speed.py` | 正/负速对称性诊断（验证 BIT15 编码） |
| `tests/` | 10 个单测（运动学 + 编码，跑法见下） |

## 快速开始

```bash
# 直接跑，键盘控制：w前 s后 a左移 d右移 z自旋 空格停 q退
# 需：ID7/8/9 舵机已设好、12V 供电、COM5 未被占用
C:\Users\21209\lerobot_venv312\Scripts\python.exe kiwi_drive.py
```

> 端口/舵机 ID 在 `kiwi_drive.py` 顶部常量（PORT/BAUD/ID_LEFT 等）改。

## 无线键盘遥控

WiFi 和 BLE 都复用 `kiwi_drive.py` 的运动学与键位映射，目标是 ESP32-S3 无线执行端。

```bash
# WiFi TCP：需要先连接 ESP32 AP（YuriArm-AP / yuriarm123）
python car_remote.py

# BLE：自动扫描 YuriArm-S3，也可用 --address 指定 MAC
python car_remote_ble.py
python car_remote_ble.py --address AA:BB:CC:DD:EE:FF
```

按键：`W/S` 前后、`A/D` 横移、`Z/X` 旋转、空格停止、`E` 急停、`Q` 退出。
远程脚本以 20Hz 持续下发 `car_drive`，退出时会先清速再 `car_stop`。

## 跑测试（无需硬件）

```bash
C:\Users\21209\lerobot_venv312\Scripts\python.exe -m unittest discover -s tests -v
```

## 关键坑（已修复，勿回退）

1. **速度编码**：STS3215 速度寄存器 = BIT15 方向 + 低 15 位幅值。
   负速必须 `encode_motor_speed(-639) → 0x827F`，**绝不能按二进制补码写**（否则被读成反向满速，左右转速不对称走弧线）。
2. **波特率**：1000000（不是手册写的 115200，以实物为准）。
3. **方位角**：WHEEL_ANGLES_DEG 由实物标定（45/180/315），不要拍脑袋改。

## 标定工具

需要重标定方位角时：
1. `scan_ids.py` — 先确认 7/8/9 都在线
2. `single_wheel_calib.py` — 看每个轮正转整车往哪滑
3. `autocalib.py` — 输入滑向，自动把结果写回 kiwi_drive.py

> 注意：autocalib.py 写回的是**同目录** kiwi_drive.py（本地 code/ 结构时需自行确认路径）。

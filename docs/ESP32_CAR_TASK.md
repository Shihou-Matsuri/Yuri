# ESP32 遥控小车（轮子）—— 协作任务

## 目标

在已有 ESP32-S3 无线执行端基础上，接入**第二块 Waveshare Bus Servo Adapter (A)**，
通过 ESP32 的 **UART2** 驱动小车的 3 个串行总线舵机（STS3215），并让笔记本
可经 WiFi / BLE 无线遥控小车。

> **2026-09-02 底盘确认：三轮 kiwi 全向底盘**（LeKiwi 4in omni 轮，舵机 ID **7/8/9**，
> **电机恒速模式**）。全向轮是连续旋转轮，位置模式（car_move 0~4095）无法驱动，
> 速度控制走新增的 **`car_drive`** 指令（写 0x2E 速度寄存器）。运动学换算
> （vx/vy/omega → 每轮 raw speed）在笔记本侧完成（见仓库 `YuriChassis/kiwi_drive.py`）。

## 当前已具备

- ESP32-S3 固件已实现小车指令组（`firmware/esp32s3_exec/protocol.cpp`）：
  - `car_status`：小车遥测（position/load/voltage/temperature + drive_mode/drive_active）
  - `car_move`：按原始位置 0~4095 移动（伺服模式），`targets={"1":...,"2":...,"3":...}`
  - `car_home`：回到中点 2048
  - `car_torque`：力矩开关
  - `car_stop` / `car_resume`：小车急停/恢复
  - `car_drive`：**电机恒速模式速度控制**（kiwi 全向轮；持续速度语义，±1800 限幅）
- `config.h`：`CAR_SERVO_IDS = {7, 8, 9}`；`REG_RUN_MODE(0x21)/REG_MOVING_SPEED(0x2E)`
- `MotionController` 与 `CarMotionController` 共用同一 `FeetechBus` 协议（`feetech_bus.*`），
  总线层新增 `writeMotorSpeed`（BIT15 幅值编码，负速度=0x8000|abs(v)，非补码）。
- 主臂（UART1）已验证可用，`txPacket` 已修复（不再清空 RX）。
- 固件安全语义：car_drive 行驶中 500ms 无指令 → **清 0 速刹停（保持扭矩）**；全局
  `estop` 联动小车刹停+置 estop；`bus_diag` 的 uart2 已按小车 ID（7/8/9）ping。

## 硬件接线

1. 第二块 Waveshare Adapter(A)：
   - 两个黄色跳线帽 → **A（UART-SERVO）**
   - 舵机 → 适配器 `D/V/G` 口
   - 外接电源 → **DC 9~12.6V**（与舵机电压一致），并与 ESP32 共地
   - **不要**用适配器 USB-C 接 ESP32（USB-C 仅供电脑 USB 模式）
2. ESP32 侧用 **三根单独的杜邦线**（不要用三针排座跨越不相邻的针）：
   - `config.h` 当前 UART2：`TX=GPIO19`、`RX=GPIO20`；若换板/换针只改这里
   - 连接：ESP32 `GPIO19` → Waveshare UART `TX`；`GPIO20` → Waveshare UART `RX`；
     ESP32 真正的 `GND` → Waveshare UART `GND`
   - 注意：GND 必须接 ESP32 板上**标 GND** 的针（通常在最下/边角），不能插到数据针。

## 验证步骤

> 固件改动后需重新编译烧录（`flash.ps1` 或 Arduino IDE）。以下验证**车体抬空**进行。

```powershell
# 1. 用板载 CH343/UART0 口（或原生 USB）确认 ESP32 在线
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_smoke.py --serial COM19 --ping-only

# 2. 总线诊断（uart2 按 CAR_SERVO_IDS=7/8/9 ping；确认接线方向/供电）
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_smoke.py --serial COM19 --diag

# 3. 小车状态（确认 drive_mode/drive_active 字段返回）
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --cmd car_status

# 4. 逐轮点动验证方向（车体抬空！ID7 正转 1 秒 → 停 → 确认轮向与本地 USB 实测一致）
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --cmd car_drive --params '{"speeds":{"7":300}}'
#   ...观察 1s 后自动发 car_drive 全 0 或 car_stop 刹停
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --cmd car_stop

# 5. 三轮回正后再全向点动：ID7=300 时整车应滑向"前左"（按 kiwi_drive.py 标定）

# 6. 键盘无线遥控（车体抬空首测三轮方向后落地）
& E:\Anaconda\envs\lerobot\python.exe YuriChassis\car_remote.py
#   W/S前后 A/D横移 Z/X旋转 空格停 E急停 Q退出
```

> `car_drive` 是持续速度：发完指令后 500ms 内没有新指令/心跳，固件自动清 0 速刹停。
> 遥控脚本应以 ≥2Hz（建议 10~20Hz）持续下发，勿手工单发后走开。

## 已知约束 / 注意事项

- 小车总线与主臂共用同一套 Feetech 协议；**同一时刻只能有一个总线做长动作**，
  否则会因半双工总线并发冲突（建议保持互斥，或由状态机串行调度）。
  遥控/导航期间主臂不得同时运动；机械臂抓取阶段小车必须已刹停（car_stop 或 0 速）。
- 舵机 ID / 供电：先用 USB 模式（B）确认 ID 与供电，再切回 A 模式接 ESP32。
- `bus_diag` 的 uart2 分支已按小车 ID（7/8/9）ping；`bus_scan` 仍只扫 UART1。
- 本地过载急停阈值在 `config.h` 的 `DEFAULT_ESTOP_LOAD`，小车可单独用 `car_stop`。
- 记得同步更新 `firmware/protocol.md` 与 `firmware/esp32s3_exec/README.md`。

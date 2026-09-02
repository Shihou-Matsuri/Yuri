# ESP32 遥控小车（轮子）—— 协作任务

## 目标

在已有 ESP32-S3 无线执行端基础上，接入**第二块 Waveshare Bus Servo Adapter (A)**，
通过 ESP32 的 **UART2** 驱动小车/轮子的 3 个串行总线舵机（STS3215），并让笔记本
可经 WiFi / BLE 无线遥控小车。

## 当前已具备

- ESP32-S3 固件已实现小车指令组（`firmware/esp32s3_exec/protocol.cpp`）：
  - `car_status`：小车遥测（position/load/voltage/temperature）
  - `car_move`：按原始位置 0~4095 移动，`targets={"1":...,"2":...,"3":...}`
  - `car_home`：回到中点 2048
  - `car_torque`：力矩开关
  - `car_stop` / `car_resume`：小车急停/恢复
- `MotionController` 与 `CarMotionController` 共用同一 `FeetechBus` 协议（`feetech_bus.*`）。
- 主臂（UART1）已验证可用，`txPacket` 已修复（不再清空 RX）。

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

```powershell
# 1. 用板载 CH343/UART0 口（或原生 USB）确认 ESP32 在线
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_smoke.py --serial COM19 --ping-only

# 2. 总线诊断（uart2 会尝试 ping ID 1~6；若小车舵机不是 1~6，用车指令单独验证）
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_smoke.py --serial COM19 --diag

# 3. 小车状态（经蓝牙示例）
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --cmd car_status

# 4. 让小车舵机（id 1/2/3）各自动一下，如到 2500
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --cmd car_move --params '{"targets":{"1":2500,"2":2500,"3":2500},"duration":2}'
```

> 若小车舵机 ID 不是 1/2/3，先改 `firmware/esp32s3_exec/config.h` 的 `CAR_SERVO_IDS`，
> 或在 USB/B 模式下用 `YuriArm/tools/waveshare_usb_ping.py` 扫 ID。

## 已知约束 / 注意事项

- 小车总线与主臂共用同一套 Feetech 协议；**同一时刻只能有一个总线做长动作**，
  否则会因半双工总线并发冲突（建议保持互斥，或由状态机串行调度）。
- 舵机 ID / 限位：先用 USB 模式（B）确认 ID 与供电，再切回 A 模式接 ESP32。
- `bus_scan` 目前只扫 UART1；扫小车总线建议用 `car_status`/`car_move` 或扩展固件。
- 本地过载急停阈值在 `config.h` 的 `DEFAULT_ESTOP_LOAD`，小车可单独用 `car_stop`。
- 记得同步更新 `firmware/protocol.md` 与 `firmware/esp32s3_exec/README.md`。

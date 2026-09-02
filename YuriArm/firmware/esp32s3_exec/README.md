# YuriArm ESP32-S3 无线执行端固件

> 里程碑 M3.5（方案设计.md）/ F1 固件基线（2026-09-02 已烧录验证）。让 ESP32-S3 成为车上"无线执行端"：
> 笔记本（YuriArm/lerobot）发 JSON 指令（**TCP / USB 串口 / BLE 三通道**），ESP32 本地执行
> （插值 + 看门狗 + 本地急停），通过总线适配器驱动主臂 6×STS3215。
>
> **已验证（真机 COM18）**：三通道 ping/status/telemetry/move_joints 全通；
> BLE 大响应分片重组正常；心跳喂狗正常、看门狗不再误触发。

## 目录

```
esp32s3_exec/
├── esp32s3_exec.ino   # 主程序：WiFi AP + TCP 服务器 + 运动循环 + 安全
├── config.h           # 引脚 / WiFi / 安全参数 / 关节表（标定）
├── feetech_bus.*      # Feetech 协议 v0 驱动（半双工，兼容 Waveshare Adapter）
├── car_motion.*       # UART2 小车 3 舵机的遥测/插值/看门狗
├── motion.*           # 归一化换算 / 插值 / 看门狗 / 急停
└── protocol.*         # JSON 指令路由（与 protocol.py / firmware/protocol.md 对齐）
```

## 构建与烧录（Arduino CLI）

```powershell
# 1) 安装工具链（一次性）
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install ArduinoJson

# 2) 编译（USB CDC 打开，日志走 USB 串口）
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc \
  YuriArm/firmware/esp32s3_exec

# 3) 烧录：ESP32-S3 原生 USB 口需手动进下载模式：
#    按住 BOOT -> 点一下 RESET -> 松开 BOOT，然后：
arduino-cli upload -p COM17 --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc \
  YuriArm/firmware/esp32s3_exec
```

## 接线（Waveshare Bus Servo Adapter (A)）

```
ESP32-S3                     Waveshare Adapter (A)      主臂总线（STS3215）
GPIO17 (UART1_TX) ─────────► UART 口 TX                  ─┐
GPIO18 (UART1_RX) ─────────► UART 口 RX                  ├─ 共地；舵机电源经适配器
GND ───────────────────────► UART 口 GND                 ┘
```

> ⚠️ 关键：这是 LeRobot 文档里的 **Bus Servo Adapter (A)**，不是 MAX485。给 ESP32
> 的接口是板子上标着 **UART** 的 3 针排针（TX/RX/GND），**不是 USB-C**。
> 两个黄色跳线帽必须放在 **A（UART-SERVO）**；如果放 B（USB-SERVO），ESP32 从这里读不到数据。
> 烧录/调试时 USB 供电即可；**驱动舵机必须外接 9~12.6V 总线电源**，且 ESP32 与舵机电源共地。

可选的小车总线（UART2）接法：

```
ESP32 GPIO15 (UART2_TX) ──► Waveshare Adapter UART TX
ESP32 GPIO14 (UART2_RX) ──► Waveshare Adapter UART RX
ESP32 GND ───────────────► Adapter UART GND
GPIO13 不接（Waveshare UART 模式无需方向脚）
```

## 使用

1. 上电后 ESP32 开 AP `YuriArm-AP`（密码 `yuriarm123`，IP 192.168.4.1）。
2. 笔记本连该 WiFi，TCP 连 `192.168.4.1:8765`，发行分隔 JSON（见 firmware/protocol.md）：

```jsonc
{"id":1,"cmd":"ping","params":{}}
{"id":2,"cmd":"status","params":{}}
{"id":3,"cmd":"move_joints","params":{"targets":{"shoulder_lift":30},"duration":2}}
{"id":4,"cmd":"telemetry","params":{}}
{"id":5,"cmd":"estop","params":{}}
{"id":6,"cmd":"car_status","params":{}}
{"id":7,"cmd":"car_move","params":{"targets":{"1":2048,"2":2048,"3":2048},"duration":1.0}}
```

`car_*` 是小车总线（UART2，id 1/2/3，原始 0~4095）的轻量控制，便于在接好适配器后
先单独验证移动。`car_torque`、`car_stop`/`car_resume` 可单独开关/急停小车。

## 安全行为

- 上电默认力矩关闭，只有收到明确 move/close_gripper 才运动；
- **500ms** 无任何指令 -> 停止并关力矩（设计值 200ms 针对 WiFi TCP；BLE/无电机总线超时场景
  下 200ms 太紧，放宽到 500ms 仍安全兜底）；执行长轨迹时笔记本需持续发 `heartbeat` 保活指令
  （只喂狗、不回包，避免 BLE 链路被 pong 流量拥塞）；
- 运动期间每 100ms 读全部关节 Present_Load，超 `estop_load` -> 本地急停（无需笔记本往返）；
- `resume` 解除急停并恢复力矩。

## 待办 / 里程碑

- [ ] F0 硬件验证：串口日志 + AP 起来（烧录后 `Serial` 打印 IP）
- [ ] F1 本基线：WiFi/TCP/JSON/ping/status/telemetry/move_joints/home/estop/resume
- [x] F2 真机总线：Waveshare Adapter(A、跳线 A、TX/RX/GND 同号) 接 UART1(GPIO17/18)
  → 6 电机 ping 全通、telemetry 位置/负载/电压/温度正确（2026-09-02 实机验证）
- [ ] F3 夹爪：close_gripper 停滞确认逻辑移植 arm.py 完整版
- [ ] F4 拾取原语 pick（姿态表存固件或笔记本下发）
- [ ] M6 小车总线 UART2（3 舵机，可选）
- [ ] 集成：YuriArm 新增 `Esp32Arm` 后端（ArmBackend 子类，走 TCP 而非 USB）


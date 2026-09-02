# YuriArm ESP32-S3 执行端 · 进度快照（2026-09-02）

> 供下次会话快速恢复现场用。

## 已完成 ✅
- 硬件：ESP32-S3（16MB Flash + 8MB PSRAM），原生 USB 口 = COM18（VID_303A&PID_1001）
- 工具链：Arduino CLI 1.5.2 + esp32 3.3.11 + ArduinoJson 7.4.3（走 dl.espressif.com 镜像装的）
- 固件 F1：`firmware/esp32s3_exec/`，三通道（TCP:8765 / USB 串口 / BLE: YuriArm-S3），
  Feetech v0 驱动、插值、500ms 看门狗、本地急停、heartbeat 保活指令、BLE 20B 分片+FIFO
- 已真机验证：串口/BLE 的 ping/status/telemetry/move_joints 全通；WiFi AP `YuriArm-AP` 正常
- 2026-09-02 新增：`car_status/car_move/car_home/car_torque/car_stop/car_resume`（UART2），
  已编译烧录到 COM18；`esp32_smoke.py --diag` 会同时测 UART1/UART2 的 TX/RX 两种方向
- **F2 真机总线已验证 ✅**：Waveshare Bus Servo Adapter (A) 跳到 A，UART 三针接
  ESP32 GPIO17(TX)/GPIO18(RX)/GND（同号直连）。`bus_raw` 6 个舵机均有应答，
  `bus_diag` 的 `uart1` 6 个 `ping=true`，`telemetry` 能读回位置/负载/电压/温度。
  关键修复：`FeetechBus::txPacket()` 不再在发送后清空 RX（原来会误把舵机应答当"回显"吞掉）；
  并新增 `bus_raw` / `bus_scan` 诊断命令。

## 当前状态 ⚠️
- 真机通过 **COM19（ESP32-S3 板载 CH343 USB-UART，对应 UART0）** 供电运行并烧录/测试；
  原生 USB-Serial/JTAG 口是 COM18。主臂总线走 UART1（GPIO17/18）。
- `uart1` 正常（6 舵机 ping=true），`uart1_swap` 为交叉方向故 `false`（正常）；
  `uart2` 尚未接小车，`false`（正常）。

## 待办 🔜（明天）
1. 问清"驱动板"型号 + 接线引脚 + 供电/共地情况（见下）
2. **关键提醒**：STS3215 总线是**单线 TTL 半双工**（VCC/GND/SIG，1Mbaud）。
   Waveshare Bus Servo Adapter (A) 本身就带方向控制，**不需要 MAX485/DE 脚**；
   ESP32 接它板上的 UART 口，跳线 A，供电 9~12.6V。
3. 主臂 UART1：TX=GPIO17、RX=GPIO18、GND；Waveshare UART 口 TX→TX、RX→RX（官方同号接法）
4. 下一步：F3 close_gripper/pick → F7 YuriArm `Esp32Arm` 后端（走 TCP）+ 多通道接线规整

## 常用命令
```powershell
# 烧录（需 BOOT+RESET 进下载模式，烧完拔插 USB 重启）
powershell -ExecutionPolicy Bypass -File YuriArm\firmware\esp32s3_exec\flash.ps1

# 测试（PC 用 USB 连 COM18）
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_smoke.py --serial COM18
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --status --telemetry

# BLE 移动测试（心跳自动喂狗）
& E:\Anaconda\envs\lerobot\python.exe YuriArm\tools\esp32_ble.py --move '{"shoulder_lift":30}' --duration 2
```

## 已知坑
- 烧录：原生 USB 口无自动下载电路，必须手动 BOOT+RESET；烧完 RTS 复位会进下载模式，需拔插 USB 才跑应用
- 用 COM19（板载 CH343/UART0）也能烧录并跑协议；`txPacket` 不能清 RX，否则吞掉舵机应答
- BLE 单条通知只有 MTU-3 字节 → 固件 20B 分片 + `\n` 分帧，客户端重组（esp32_ble.py 已实现）
- BLE 回调不能做总线操作（与主循环并发访问 UART1 会卡死）→ 指令统一主循环处理
- 无电机时总线读写每次超时 20ms，插值/遥测明显变慢（正常现象，接电机后恢复）

# YuriArm 无线执行端（ESP32-S3）协议规范（草案）

> 状态：**协议已定；固件 F1 基线已实现并真机验证（里程碑 M3.5，2026-09-02）**。
> 固件代码见 `firmware/esp32s3_exec/`（TCP + USB 串口 + BLE 三通道 + JSON 路由 + Feetech v0 驱动 + 插值/看门狗/急停）。
> 本文是 `yuriarm/protocol.py` 的配套说明，以 Python 侧为唯一事实来源（Single Source of Truth），
> 固件指令路由见 `firmware/esp32s3_exec/protocol.cpp`，二者必须保持同步。

## 1. 拓扑

```
笔记本（感知/规划/指令）  --WiFi TCP-->  ESP32-S3（轨迹缓冲/看门狗/本地急停）
                                          |--UART1+适配器--> 从动臂总线（6×STS3215）
                                          |--UART2+适配器--> 小车总线（3 舵机，可选）
```

- ESP32-S3 开 WiFi AP，笔记本直连；TCP 可靠传输，行分隔 JSON。
- 关键设计：**整段轨迹下发 + 本地执行**（TRAJ→GO），WiFi 抖动不影响中途动作；
  500ms 心跳看门狗断线即停；本地急停读舵机负载，碰撞瞬间停止回退。

> 适配器：LeRobot/Waveshare **Bus Servo Adapter (A)**。ESP32 必须接板上的 **UART
> 3 针口（TX/RX/GND）**，两个黄色跳线帽放在 **A（UART-SERVO）**；USB-C 仅供电脑 USB 模式。

## 2. 报文（行分隔 JSON，UTF-8）

与 `yuriarm/protocol.py` 的 `Command` / `CommandResult` 结构一致：

```jsonc
// 下行（笔记本 → ESP32）
{"id": 1, "cmd": "move_joints", "params": {"targets": {"shoulder_lift": 30.0}, "duration": 2.0}}
{"id": 2, "cmd": "estop",       "params": {}}
{"id": 3, "cmd": "ping",        "params": {}}

// 上行（ESP32 → 笔记本）
{"id": 1, "ok": true,  "result": {"positions": {"shoulder_lift": 30.0}}, "error": null}
{"id": 3, "ok": true,  "result": {"pong": true}, "error": null}
```

## 3. 指令表（固件需实现子集）

| cmd | 说明 | params |
|---|---|---|
| ping | 连通性 | {} |
| status | 状态（已连接/力矩/看门狗） | {} |
| move_joints | **插值**移动到目标关节角（脚本化单次移动用） | targets, duration? |
| teleop_joints | **直写**遥操作：6 关节归一化目标直接写 Goal_Position，无插值/无读回/不回包 | targets |
| move_to_pose | 移动到命名姿态（固件内置姿态表） | pose |
| open_gripper / close_gripper | 夹爪（close 用负载判定） | close: max_load?, timeout? |
| pick | 本地执行完整拾取周期 | pick_high?, pick_low?, drop? |
| home | 回安全位 | {} |
| estop / resume | 急停 / 恢复 | {} |
| telemetry | 遥测（位置/负载/电压/温度） | {} |
| bus_diag | 诊断 UART1/UART2：回显 + 逐 ID ping | {} |
| bus_scan | 全 ID 扫描 UART1，查找从动臂实际舵机 | {} |
| bus_pos / bus_goto | 读/写单舵机原始寄存器（诊断/重标定 range 用） | id, addr / raw |
| car_scan | 全 ID 扫描 UART2 当前/交换方向，查找小车实际舵机 | {} |
| car_status | 小车遥测（id/position/load/电压/温度） | {} |
| car_move | 小车按原始位置移动（伺服模式） | targets={"7":...,"8":...,"9":...}, duration |
| car_home | 小车回到中点 2048 | duration |
| car_torque | 小车力矩开关 | on=true/false |
| car_stop / car_resume | 小车急停/恢复 | {} |
| car_drive | 小车电机恒速模式速度控制（kiwi 全向轮） | speeds={"7":300,"8":-150,"9":0} 或 raw=[...], 范围 ±1800 |

> 无线版把 `move_joints`/`pick` 解析为本地轨迹缓冲（每关节时间戳+目标），`GO` 语义由
> `move_joints` 本身承担（收到即开始执行）；`estop` 由 ESP32 侧 200ms 看门狗 + 本地负载
> 监测兜底。`run`/`scan`/`calibrate` 属于笔记本侧，不下发固件。

### teleop_joints（直写遥操作，2026-09-04 新增）

主动臂 → 从动臂**实时遥操作**专用：把 6 关节归一化目标（`targets` 键值同 move_joints）
直接转 raw 写 `Goal_Position`——**不做固件插值**（舵机内部速度控制自行平滑）、
**不读回位置**、**不回包**。每帧覆盖为最新目标，天然无积压。

- 为什么不是 move_joints：插值状态机在"真 leader 多关节持续大幅变化"下会卡死
  （续目标边界 bug 修了 6+ 轮，根因是状态机本身不适合遥操作）。见 `SOUL.md`。
- 遥操作桥（leader_remote.py）默认发本指令；move_joints 保留给脚本化单次移动。
- 帧即喂狗；断连 500ms 由看门狗急停（watchdog 覆盖 `teleopActive` 状态，
  与插值中同等对待）。
- 响应被抑制（与 heartbeat/car_drive/move_joints 一致），需要状态用 status/telemetry 轮询。

### 高频指令回包抑制（2026-09-04）

`heartbeat`、`car_drive`、`move_joints`、`teleop_joints` 四条高频指令**不回包**。
20Hz 遥操作若每条回 JSON，响应堆积会淹没 ping pong，导致客户端误判断连重连。
固件实现见 `esp32s3_exec.ino` 的 `processCommandLine`。

### car_drive（小车电机恒速模式，2026-09-02 新增）

三轮 kiwi 全向轮等**连续旋转轮**无法用位置模式（car_move 的 0~4095 插值）驱动，
必须走电机恒速模式：写运行模式寄存器 0x21=1 后，用速度寄存器 0x2E 控制轮速
（BIT15=方向位，低 15 位=幅值，**不是补码**——负速度编码为 `0x8000|abs(v)`）。

- `car_drive` 是**持续速度**语义（非插值）：收到即写速度，车保持该速度直到下一条
  car_drive / car_stop / 看门狗超时。笔记本应以固定频率（建议 ≥2Hz，遥控建议 10~20Hz）
  持续下发速度或心跳；**500ms 无任何指令 → 固件自动清 0 速刹停**（保持扭矩防溜坡）。
- 首次 car_drive 自动切电机模式（幂等）；car_move/car_home 前若在电机模式会自动切回
  伺服模式。两种指令流任意顺序安全，但**不要混用**（模式切换有总线开销）。
- 速度值范围 ±1800（CAR_SPEED_LIMIT，与 PC 侧 `kiwi_drive.py` 的 MAX_RAW_SPEED 一致）；
  运动学换算（vx/vy/omega → 每轮 raw speed）在**笔记本侧**完成，固件只写寄存器。
- `car_status` 新增 `drive_mode`（是否已切电机模式）与 `drive_active`（是否行驶中）。
- 安全：全局 `estop` 会联动小车清速刹停并置 estop（需 `resume` 后才能再 car_drive，
  速度不自动恢复）；`car_stop` = 刹停 + 扭矩关。

## 4. 安全（固件硬性要求）

1. 上电默认力矩关闭、回安全位；只有收到明确 move/pick 才运动。
2. 500ms 未收到任何指令/心跳 → 立即停止并回安全位。
3. 本地负载监测：任一关节 Present_Load 超阈值 → 本地停止回退（不等笔记本）。
4. 半双工方向切换：由 Waveshare Adapter (A) 自动完成；固件发完包后切回接收并丢弃
   单线 TTL 回显；参考 lerobot `feetech.py` 协议移植。

## 5. 遥测字段（与 arm.py 的 telemetry() 对齐）

```jsonc
{"positions": {"shoulder_pan": 0.0, "...": 0.0},
 "loads":      {"gripper": 12.0, "...": 0.0},
 "voltage": 7.4, "temperature": 35.0, "torque_on": true}
```

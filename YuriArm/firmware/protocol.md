# YuriArm 无线执行端（ESP32-S3）协议规范（草案）

> 状态：**协议已定；固件 F1 基线已实现并真机验证（里程碑 M3.5，2026-09-02）**。
> 固件代码见 `firmware/esp32s3_exec/`（TCP + USB 串口 + BLE 三通道 + JSON 路由 + Feetech v0 驱动 + 插值/看门狗/急停）。
> 本文是 `yuriarm/protocol.py` 的配套说明，以 Python 侧为唯一事实来源（Single Source of Truth），
> 固件指令路由见 `firmware/esp32s3_exec/protocol.cpp`，二者必须保持同步。

## 1. 拓扑

```
笔记本（感知/规划/指令）  --WiFi TCP-->  ESP32-S3（轨迹缓冲/看门狗/本地急停）
                                          |--UART1+适配器--> 主臂总线（6×STS3215）
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
| move_joints | 插值移动到目标关节角 | targets, duration?, max_velocity? |
| move_to_pose | 移动到命名姿态（固件内置姿态表） | pose |
| open_gripper / close_gripper | 夹爪（close 用负载判定） | close: max_load?, timeout? |
| pick | 本地执行完整拾取周期 | pick_high?, pick_low?, drop? |
| home | 回安全位 | {} |
| estop / resume | 急停 / 恢复 | {} |
| telemetry | 遥测（位置/负载/电压/温度） | {} |
| bus_diag | 诊断 UART1/UART2：回显 + 逐 ID ping | {} |
| car_status | 小车遥测（id/position/load/电压/温度） | {} |
| car_move | 小车按原始位置移动 | targets={"1":...,"2":...,"3":...}, duration |
| car_home | 小车回到中点 2048 | duration |
| car_torque | 小车力矩开关 | on=true/false |
| car_stop / car_resume | 小车急停/恢复 | {} |

> 无线版把 `move_joints`/`pick` 解析为本地轨迹缓冲（每关节时间戳+目标），`GO` 语义由
> `move_joints` 本身承担（收到即开始执行）；`estop` 由 ESP32 侧 200ms 看门狗 + 本地负载
> 监测兜底。`run`/`scan`/`calibrate` 属于笔记本侧，不下发固件。

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



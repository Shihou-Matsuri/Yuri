# SOUL.md — Yuri 项目的设计灵魂与血泪教训

> 给未来在此仓库工作的任何 agent / 维护者。先读这里，再动代码。
> 本文件记录的不是功能清单，而是**为什么这么做**和**我们付出什么代价才知道**。

## 一句话

Yuri = 笔记本（感知/规划/遥操作）→ ESP32-S3（无线执行端）→ 舵机总线（机械臂 6×STS3215 / 小车 3 舵机）的模块化机器人。仓库里每一行代码都服务于"笔记本发意图、ESP32 可靠执行"这一分工。

## 核心架构决策（每条都有血的教训）

### 1. 遥操作必须"直写最新目标"，禁止插值状态机

- **做法**：遥操作桥（`YuriArm/tools/leader_remote.py` → `leader_bridge.py`）每帧发
  `teleop_joints`，固件直接把 6 关节归一化目标转 raw 写 `Goal_Position`，
  **无插值、无读回、无回包**。舵机内部自带速度控制，自行平滑到达。
- **为什么**：早期用插值 `move_joints`（固件 20Hz tick 从 from_ 走向 to_），
  在"真 leader 多关节持续大幅变化"下反复卡死：插值中途收到新目标要续走，
  续走逻辑（from_ 推算、限速步进、tick 时序）每一版都有边界 bug，
  修了 6+ 轮（限速、lastRaw_ 追踪、跳过读回、防积压、抑制回包）才明白——
  **问题不在某个 bug，在插值这个状态机根本不适合遥操作**。
- **教训**：遥操作是"每帧覆盖最新目标"的语义，天然无状态；
  插值是为"脚本化单次移动"设计的，硬套到遥操作上就是给自己造状态机 bug。
  lerobot 官方 teleoperate 就是直写，我们绕了一大圈才回到正轨。

### 2. 高频指令一律不回包

- `heartbeat`、`car_drive`、`move_joints`、`teleop_joints` 都**不回包**
  （见 `esp32s3_exec.ino` processCommandLine 的抑制逻辑）。
- **为什么**：20Hz 遥操作若每条回 JSON，响应在 TCP/USB 上堆积，
  淹没 ping pong → 客户端误判断连 → 恶性重连循环（轮子 WiFi 版真实现场翻车）。
- 需要状态时主动 `status`/`car_status`/`telemetry` 轮询（这些仍回包）。

### 3. ESP32 是单线程主循环，任何"一次处理完"都是陷阱

- `handleStream` 每轮最多处理 16 行（`MAX_LINES_PER_CYCLE`）；
  看门狗 500ms 覆盖 `interpActive()` 和 `teleopActive()` 两种运动态。
- **为什么**：曾有一次把串口积压全 drain，heartbeat 排在队尾被饿死 → 看门狗误触发。
- ESP32 上电默认力矩关，必须显式 `resume` 才开扭矩（协议安全 #1）。

### 4. 链路通道要克制

- 当前固件 **BLE 已禁用**（用户决策：只留 WiFi，减射频/CPU 干扰与固件体积 ~22%）；
  指令口 USB 115200（1M 实测 CH343 丢字节不稳，已回退）。
- 小车 car_drive 走电机恒速模式（速度寄存器 BIT15 方向 + 低 15 位幅值，非补码）。

## 真机联调铁律（每一条都是现场事故换来的）

1. **单实例锁**：同一串口只允许一个 leader_remote/car_remote。
   多进程抢 COM8 → 指令淹没 → 从动臂"卡死"假象。启动会检查 pid 锁文件。
2. **测试时机要对齐**：让用户"大幅转 leader"时必须明确喊开始/结束，
   否则读数恒定是"用户没转"，不是 bug。
3. **改完固件先单独验证** `move_joints`/`teleop_joints` 能驱动从动臂，再上桥。
   曾经改完没验证就上桥，用户报"完全不动"。
4. **从动臂/主动臂供电接触**历史多次出问题（只读到部分舵机 ID、
   读数恒 0/恒 2048）——先查供电再查代码。
5. **重开串口会复位 ESP32**（DTR/RTS），读到 boot 日志不代表崩溃。
6. 主动臂 gripper 舵机偶发读数恒 0/离线——先物理重插再怀疑软件。
7. 大幅动作"卡住"先查 `status` 的 `estop`/`watchdog_ok`，再查负载，
   别直接猜参数。
8. **轮子"停" = 持续下发 0 速（car_drive [0,0,0]）**，不能只发 heartbeat：
   固件 heartbeat 同时喂小车 watchdog，只发 heartbeat 会让小车保持最后速度
   （dual_remote 空格停不住，真机踩过；car_remote 一直发 0 速所以没事）。
9. **急停分范围**：全局 estop 关从动臂扭矩并置位，恢复须显式 resume；
   dual_remote 的 E 只急停轮子（car_stop），否则按 E 后机械臂"连接失效"。

## 安全底线（不许为了功能牺牲）

- 500ms 无有效指令 → 看门狗 → 停 + 关扭矩（协议.md 硬性要求，不许放宽到消失）。
- `estop_load` 2000（接近堵转 2047）：放行正常大幅运动，仍保真堵转保护。
- 从动臂与小车互斥：桥运行时 car_drive 不得运行（半双工总线）。
- car_remote 收尾用 `car_drive [0,0,0]` 刹停，不用 `car_stop`（car_stop 置 estop，
  下次 car_drive 被拒需 resume）。

## 环境事实（本机 2026-09）

- 本机 venv：`C:\Users\21209\lerobot_venv312`（python.exe 曾损坏为 0 字节，
  用 venvlauncher 修复——**venv 的 python.exe 是 launcher，不是完整 exe**）。
- 主动臂 COM7（CH343）/ ESP32 COM8（115200 指令口）。
- 烧录：`arduino-cli upload -p COM8 --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc`，
  需用户 BOOT+RESET。
- 学校网络 TLS MITM：装包用 pip 系统证书，uv/rustls 会失败。

## 调试方法论（本次最大的教训）

- 补丁 ≥3 个还治不好同一症状 → **强制架构复盘**，不是继续打补丁。
- 测试必须复现**真实负载特征**：fake leader 要模拟"多关节同时大幅跳变+抖动"，
  不能只发固定值/平滑正弦——那会给出虚假的"链路没问题"结论。
- 频繁"有进展"但症状反复 = 方向可能错了。诚实承认比持续小修有价值。
- 每加一层代码先问"它存在的理由"；遥操作直写是生态标准，插值是画蛇添足。

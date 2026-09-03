# 主动臂遥控从动臂：交接任务

> 目标：主动臂（leader）接在电脑上，由人握着操作；电脑读取主动臂关节角，
> 通过 YuriArm 的 ESP32-S3 无线执行端远程驱动从动臂（follower）。
> 本任务交给合作者实现，当前仓库只有相关参考，还没有 PC-ESP32 遥操作链路。

## 1. 结论先行

需要新增一个 **PC 侧遥操作桥**：

```text
主动臂 SO101Leader (USB/COM)
        |
        | get_action() 读取 Present_Position
        v
PC 遥控循环：映射 + 限位 + 平滑 + 安全
        |
        | WiFi TCP 192.168.4.1:8765 或 BLE YuriArm-S3
        v
ESP32-S3 firmware: move_joints / telemetry / estop
        |
        v
SO101Follower / 6×STS3215 (UART1, GPIO17/18)
```

现有 `LeKiwiTeleop` 是有线版参考，**不能**直接完成上述任务，因为它要求主动臂和
从动臂都直连电脑；本任务要求从动臂走 ESP32 无线执行端。

## 2. 硬件现状

### 2.1 主动臂

- SO-101 leader，6×STS3215：
  `shoulder_pan / shoulder_lift / elbow_flex / wrist_flex / wrist_roll / gripper`
- USB 控制板直连电脑，只读取角度，**不输出力矩**
- LeRobot 接口：`lerobot.teleoperators.so101_leader.SO101Leader`
- 读取入口：`leader.get_action()`
  - 返回值形如：`{"shoulder_pan.pos": 12.3, ..., "gripper.pos": 40.0}`
  - 使用方法：去掉键尾部的 `.pos`，再映射到 YuriArm 的 `JOINT_NAMES`
- 归一化单位：
  - 身体关节：`-100..100`
  - gripper：`0..100`

### 2.2 从动臂

- SO-101 follower，6×STS3215
- 当前由 ESP32-S3 的 UART1 驱动：
  - ESP32 GPIO17 -> Waveshare Adapter UART TX
  - ESP32 GPIO18 -> Waveshare Adapter UART RX
  - 跳线 A（UART-SERVO），1 Mbps
- 固件协议是行分隔 JSON：
  - `{"cmd":"move_joints","params":{"targets":{...},"duration":0.05}}`
  - `{"cmd":"telemetry","params":{}}`
  - `{"cmd":"estop","params":{}}`
  - `{"cmd":"resume","params":{}}`
- 可复用现有工具：
  - `YuriArm/tools/esp32_smoke.py`
  - `YuriArm/tools/esp32_ble.py`
  - `YuriChassis/car_remote.py`：WiFi TCP 持续发送模式参考
  - `YuriChassis/car_remote_ble.py`：BLE 持续发送模式参考

## 3. 建议实现

建议新增：

```text
YuriArm/
├── yuriarm/leader_bridge.py      # 主动臂读取、映射、安全、发送
├── yuriarm/esp32_transport.py    # WiFi TCP / BLE / USB 三种传输（可复用现有模式）
├── configs/leader.json           # leader 端口、id、频率、限位、映射
├── tools/leader_remote.py        # 命令行入口
└── tests/test_leader_bridge.py   # 无硬件测试
```

### 3.1 推荐循环

建议以 `30–60 Hz` 读取主动臂，以 `20 Hz` 向 ESP32 发送目标：

```python
action = leader.get_action()
targets = normalize_and_safe_map(action)
send_move_joints(targets, duration=1.0 / 20.0)
```

`move_joints` 的 `duration` 应和发送频率匹配；发送失败、主动臂断连、按键急停时，
PC 应立即发送 `estop`，ESP32 端同时有 500 ms 看门狗兜底。

### 3.2 映射要求

- 主动臂每个 `.pos` 值与从动臂同名字节必须映射在 `-100..100` / `0..100`
- 必须读取 `YuriArm/config.py` 中的 `JOINT_NAMES`，不要硬编码关节列表
- 增加死区（建议 `0.5..1.0`），避免主动臂轻微抖动造成从动臂持续抖动
- 增加速度限幅，默认不超过 `config.py` 的 `safety.max_velocity`
- 增加关节限位截断，防止从动臂越界
- `gripper` 需要单独映射，并先做一次开/合方向校核

### 3.3 传输实现

至少实现其中一条，建议同时支持：

| 方式 | 地址 | 参考 |
|---|---|---|
| WiFi TCP | `192.168.4.1:8765` | `YuriChassis/car_remote.py` |
| BLE | `YuriArm-S3` | `YuriChassis/car_remote_ble.py` |
| USB UART0 | `COM20 / 115200` | `YuriArm/tools/esp32_smoke.py` |

所有传输只负责发送 JSON 行，不应重复实现协议解析。

## 4. 已有接口核对

主动臂读取接口已在本仓库源码中：

```text
src/lerobot/teleoperators/so101_leader/so101_leader.py
```

核心方法：

```python
leader.get_action()
```

从动臂侧可参考：

```text
src/lerobot/robots/so101_follower/so101_follower.py
YuriArm/yuriarm/arm.py
YuriArm/firmware/protocol.md
```

注意：`YuriArm` 不修改 lerobot 源码；只在真机路径惰性导入
`SO101Follower`，主动臂侧也应采用同样的惰性导入方式。

### 4.1 合作者已提交的参考实现

合作者已上传 `LeKiwiTeleop/teleop_so101.py`（提交 `bb8021258`），可以作为
“主动臂读角度 -> 从动臂写角度”的参考。但当前版本：

- 使用老版 LeRobot 接口 `lerobot.teleoperators.so_leader` /
  `lerobot.robots.so_follower`，与本仓库当前 API
  `so101_leader` / `so101_follower` **不一致**；
- 只支持主动臂和从动臂都直连电脑的**有线遥操作**，没有经过 ESP32；
- 没有安全限位、死区、速度限幅和与小车互斥逻辑。

因此该文件应定位为 “leader 读取参考”，不能直接作为本任务的最终实现。
本任务最终应把 follower 端替换为 ESP32 `move_joints` 传输。

## 5. 验收标准

1. 主动臂接电脑后，`get_action()` 能以 `≥30 Hz` 读取且无异常退出。
2. 从动臂能跟随主动臂动作，延迟 `≤100 ms`（本机 WiFi/BLE）。
3. 动作过程中从动臂不越限、不抖动；gripper 方向经过实测确认。
4. 主动臂拔线、断连或用户按急停后，从动臂在 `≤500 ms` 内停止。
5. 与 `YuriChassis` 小车互斥：从动臂运动期间小车不可动，小车运动期间从动臂不可动。
6. `--mock` 模式可在无硬件下跑通完整循环。
7. 联调日志中能清楚看到：leader pos -> mapped targets -> ESP32 OK。

## 6. 硬性约束

- 不修改 lerobot 上游源码，只通过公共接口 `SO101Leader` / `SO101Follower` 工作。
- 禁止硬编码端口和关节表；端口放到 `configs/leader.json`，关节表复用 `config.py`。
- 不允许只写“当前能跑”的临时逻辑：传输、映射、安全都要可替换、可测试。
- 修改后必须更新 `YuriArm/README.md`、`YuriArm/docs/方案设计.md` 和本任务文档。
- 涉及新状态或共享总线时，必须评估受影响的模块：
  - `YuriArm`：`arm.py / protocol.py / server.py / cli.py`
  - `YuriArm` 固件：`protocol.cpp / esp32s3_exec.ino`
  - `YuriChassis`：小车遥控与急停

## 7. 建议交付物

1. `leader_bridge.py`：主动臂读取、映射、安全、状态管理
2. `esp32_transport.py`：WiFi/BLE/USB 统一传输接口
3. `leader.json`：主动臂与云台/端口/频率配置
4. `leader_remote.py`：命令行启动入口
5. `test_leader_bridge.py`：Mock leader + Mock transport 测试
6. 更新根仓库 `docs/` 和 README，标记该功能完成/待联调

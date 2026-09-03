# Yuri 路线图

状态图例：✅ 完成 / 🔜 进行中 / ⏳ 待办

| 里程碑 | 内容 | 状态 |
|---|---|---|
| F0 | ESP32-S3 硬件验证（串口 / AP） | ✅ |
| F1 | 固件基线：WiFi/TCP/USB/BLE + JSON + 插值 + 看门狗 + 急停 | ✅ |
| F2 | 真机总线：Waveshare Adapter(A) + UART1 驱动 6×STS3215，遥测正确 | ✅ |
| M2 | 夹取原语（close_gripper 停滞确认、pick 示教-回放） | 🔜（close_gripper 逻辑待修） |
| M3.5 | 无线执行端（三通道 + 本地执行 + 安全） | ✅ |
| M6 | 小车总线 UART2：3 舵机（`car_*` 指令已在固件，待真机接线/验证） | ⏳ |
| M7 | 集成 YuriArm `Esp32Arm` 后端（TCP/BLE 遥控整机） | ⏳ |
| V1 | YuriEye 感知接入 YuriArm（手眼标定 + 目标检测 → 抓取） | ⏳ |
| G1 | 机械臂 + 轮子 + 摄像头协同（自主拾取已放） | 🔜 |
| U1 | 综合遥控台：需求 + GUI 风格定稿（MatsuriVoice 风格） | ⏳ |
| U2 | 综合遥控台实现：连接/状态/单控/视觉/标定 5 区 | ⏳ |

## 说明

- 固件 `car_*` 指令（car_status/car_move/car_home/car_torque/car_stop/car_resume）已实现，
  但小车总线尚未真机接线。协作方按 `docs/ESP32_CAR_TASK.md` 完成接线与验证。
- 已知待修：`close_gripper` 停滞检测在“初始负载已超阈值”时会误判（需先移到中间再按负载爬升判断）。
- 已知待办：YuriArm 关节标定（部分关节读数接近 ±100，需把 `configs/arm.json` 的 joint_limits 与实体对齐）。

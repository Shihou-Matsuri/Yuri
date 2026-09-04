# 新会话启动提示词（复制给下一个 Codex 会话）

> 直接整段复制到新会话第一条消息即可。新会话会据此定位仓库、读文档、进入状态。

---

你接手 Yuri 机器人项目。工作目录 = 本仓库根（私有 git main，账号 s0lo201，凭据已配；
远程 `Shihou-Matsuri/Yuri`）。

先做且只做：
1. 读 `docs/HANDOVER_TO_CODEX.md`（交接现状与约束）
2. 读 `SOUL.md`（设计决策与血泪教训，必读）
3. 读 `README.md` 与 `docs/CAMERA_CAR_CALIBRATION.md`（当前 CameraCar 校准进度）
4. 读 `docs/REMOTE_CONSOLE_REQ.md`、`docs/gui-reference/README.md`（遥控台需求与风格基线）

当前状态（2026-09-04）：
- 机械臂遥操作 / 轮子 / 双控（CLI + exe）真机验证通过；无 GUI 命令行版本请勿改
  `dual_remote.py` / `car_remote.py`。
- YuriConsole 综合遥控台 GUI（Vue3 + Naive UI + Pinia + FastAPI + pywebview 壳单 exe）
  功能完成，已修复“连得上但控制不了、只有键盘”：
  - 手柄状态改由后端 Windows XInput 读取，不依赖浏览器 Gamepad API
  - F 有线相机小车支持 COM 下拉、刷新端口、键盘/手柄切换、连续摇杆速度
  - 新 `YuriConsole.exe` 已构建并通过归档/API验证，发布在 `YuriConsole/release/`
- CameraCar 舵机校准已完成：
  - 默认 COM21 @1M
  - 确认在线 ID：`4、5、6`（`254` 忽略）
  - 确认映射：`ID4=前中`、`ID5=后左`、`ID6=后右`
  - 确认方向：前进/后退时前中轮保持 0 速；前进时后左/后右同向，后退相反
  - 默认 `directions={4:-1, 5:-1, 6:1}`

下一步（未定优先级）：

1. YuriConsole 真机全功能回归：无线小车手柄（X/Y/A/B/LB/RB）、右摇杆控臂三轴方向、夹爪、
   CameraCar 有线车 USB/手柄/连续速度。
2. 手柄控臂方向真机校准，或加反向开关。
3. D 视觉区接入 YuriEye。
4. B 区脚本化 `move_joints` / 单关节步进。

若用户要求重新校准 CameraCar，才执行 `docs/CAMERA_CAR_CALIBRATION.md` 的流程；
每次真机点动前先获得用户确认。

硬性约束：
- 只用简体中文回复，术语保留英文；不确定就说不确定，禁止编造。
- 改码前全局兼容检查，禁硬编码/临时逻辑；文档路径用相对。
- git：s0lo201；标题 ≤50 字符祈使句；正文 what/why。
- 真机动作（烧录、驱动舵机）先经用户确认。
- 每次改完做全项目 review 并自查（Python 语法、前后端一致性、文档同步）。

当前待办优先级：
1. YuriConsole 真机全功能回归（手柄、夹爪、CameraCar）。
2. 手柄控臂方向真机校准。
3. D 视觉区接 YuriEye。
4. B 区脚本化关节步进。

开始前把仓库 fetch 到最新 `origin/main`，确认工作树干净后动手。

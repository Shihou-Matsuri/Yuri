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
- **CameraCar 舵机重新校准未完成**：
  - 默认 COM21 @1M
  - 只读扫描确认在线 ID：`4、5、6`（`254` 忽略）
  - 上一版映射为 `ID5=前中`、`ID6=后左`、`ID4=后右`
  - `ID4` 已于低速点动 2 秒，但用户尚未确认位置和方向

下一步（按顺序，不要跳步）：

1. 先向用户确认：`COM21` 是否在线、车体是否已抬空/允许低速动作。
2. 只读扫描确认当前实际 ID：
   ```powershell
   .\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --scan
   ```
3. 单独点动 `ID4`，结束后必须停轮并关扭矩：
   ```powershell
   .\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --one-wheel 4 --duration 2.0 --test-rpm 20
   ```
4. 等待用户确认 `ID4` 是“前中 / 后左 / 后右”，以及正转方向是否正确。
5. 用同样方式依次测 `ID5`、`ID6`，每测完一个等用户确认，不要连续跑。
6. 三个 ID 都确认后，把结果写入 `YuriChassis/camera_car_drive.py`：
   - `front_id`
   - `rear_left_id`
   - `rear_right_id`
   - `directions`
7. 更新 `YuriChassis/README.md`、`YuriConsole/README.md` 和校准表。
8. 运行：
   ```powershell
   .\lerobot_venv312\Scripts\python.exe -m unittest discover -s YuriChassis\tests -v
   cd YuriConsole/frontend
   npm.cmd run build
   ```
9. 若前端/后端映射改变，重建 `YuriConsole.exe`；更新 SHA256。
10. 提交推送，并更新 `docs/HANDOVER_TO_CODEX.md` 和 `docs/NEXT_SESSION_PROMPT.md`。

硬性约束：
- 只用简体中文回复，术语保留英文；不确定就说不确定，禁止编造。
- 改码前全局兼容检查，禁硬编码/临时逻辑；文档路径用相对。
- git：s0lo201；标题 ≤50 字符祈使句；正文 what/why。
- 真机动作（烧录、驱动舵机）先经用户确认。
- 每次改完做全项目 review 并自查（Python 语法、前后端一致性、文档同步）。

当前待办优先级：
1. 完成 CameraCar 舵机校准并写回映射/方向。
2. YuriConsole 真机全功能回归（手柄、夹爪、CameraCar）。
3. 手柄控臂方向真机校准。
4. D 视觉区接 YuriEye。
5. B 区脚本化关节步进。

开始前把仓库 fetch 到最新 `origin/main`，确认工作树干净后动手。

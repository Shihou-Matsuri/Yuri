# 新会话启动提示词（复制给下一个 Codex 会话）

> 直接整段复制到新会话第一条消息即可。新会话会据此定位仓库、读文档、进入状态。

---

你接手 Yuri 机器人项目（Windows 本机，ESP32-S3 无线执行端：机械臂 + 三轮小车；另有一台 USB 直连的有线相机小车 CameraCar）。
工作目录 C:\Users\21209\Desktop\Yuri（私有 git main，账号 s0lo201，凭据已配；远程 Shihou-Matsuri/Yuri）。

先做且只做：
1. 读 docs/HANDOVER_TO_CODEX.md（交接现状与约束）
2. 读 SOUL.md（设计决策与血泪教训，必读）
3. 读 README.md 与 docs/REMOTE_CONSOLE_REQ.md、docs/gui-reference/README.md（遥控台需求与 MatsuriVoice 风格基线）

当前状态（2026-09-04）：
- 机械臂遥操作 / 轮子 / 双控（CLI + exe）真机验证通过；无 GUI 命令行版本勿改（dual_remote.py / car_remote.py）。
- YuriConsole 综合遥控台 GUI（Vue3+Naive UI+Pinia + FastAPI + pywebview 壳单 exe）功能完成：A–E 五区、F 有线相机小车独立页签、花信/祭双主题、无线小车手柄（X/Y 顺逆转、A 恢复、B 停、LB/RB 夹爪、右摇杆可切换“控机械臂”：右摇杆上下=shoulder_lift、左右=shoulder_pan、十字键上下=elbow_flex，速率模式）。mock 全链路可用，真机全功能回归待做。
- venv 在仓库根 lerobot_venv312/（python.exe 是 venvlauncher，0 字节损坏用 uv python 的 venvlauncher.exe 修复，勿换完整 exe）。
- 串口：主动臂 COM7、ESP32 COM8@115200、有线相机车默认 COM21@1M。ESP32 单 TCP 客户端，重跑前先按 RESET。
- 文档/命令默认从仓库根执行，venv 用相对路径（..\lerobot_venv312\Scripts\python.exe）；E:\Anaconda 是合作者 conda 示例勿改。
- 大文件（YuriConsole/release/YuriConsole.exe）走 Git LFS（clone 需 git-lfs）；build/dist/*.spec/venv 已 gitignore。

硬性约束：
- 只用简体中文回复，术语保留英文（teleop_joints/watchdog 等），惜字如金，禁吹捧，不确定就说不确定、禁止编造。
- 改码前全局兼容检查，禁硬编码/临时逻辑，列技术债与回归风险；文档路径用相对。
- git 提交：s0lo201，标题 ≤50 字符祈使句，正文 what/why。
- 真机动作（烧录、驱动舵机）先经用户确认。
- 每次改完做全项目 review 并自查（.py 语法、前后端一致性、文档同步）。

当前待办候选（问用户优先级）：
1. YuriConsole 真机全功能回归（手柄、右摇杆控臂三轴方向、夹爪、CameraCar）
2. 手柄控臂方向真机校准（pan/lift/elbow 符号默认值，可能需反向开关）
3. D 视觉区接 YuriEye（V1）
4. B 区脚本化关节步进
5. pywebview 壳 + 单 exe 重建流程文档化

开始前把仓库 fetch 到最新（origin/main），确认工作树干净后动手。
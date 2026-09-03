# 交接文档 — 给 Codex（更新 2026-09-04 晚）

> 本仓库 `Shihou-Matsuri/Yuri`（私有 main）。给下一个会话：先读本文件 + `SOUL.md` + `README.md`，
> 再动任何代码。仓库根：本仓库根目录（git 凭据已配，s0lo201）。

## 0. 一句话现状

- **机械臂遥操作 / 轮子 / 双控（CLI 与 exe）✅ 真机验证**（dual_remote 修复过 stop/exit/E 三 bug）。
- **YuriConsole 综合遥控台 GUI（U2）功能完成**：A–E 五区 + F 有线相机小车独立页签、MatsuriVoice
  花信/祭双主题、无线小车手柄（X/Y 顺逆转、A 恢复、B 停、LB/RB 夹爪）、右摇杆可切换“控机械臂”
  （pan/lift/elbow 三轴速率，十字键前后）+ 单 exe。**mock 全链路可用；真机全功能回归待做。**
- 下次接手的会话请用 `docs/NEXT_SESSION_PROMPT.md` 的提示词启动。

## 1. 架构（简短）

笔记本 →（WiFi TCP 192.168.4.1:8765 / USB COM8@115200）→ ESP32-S3：
  UART1 → 从动臂 6×STS3215（遥操作 teleop_joints 直写，主动臂 COM7 读取）
  UART2 → 无线小车 3 舵机 ID7/8/9（car_drive 电机恒速）
另有 **有线相机小车（CameraCar）**：USB 直连 Feetech 总线（默认 COM21@1M，ID5 前中/6 后左/4 后右），
独立于 ESP32 链路。YuriEye 视觉未接入 GUI（V1 待做）。

## 2. 代码地图

| 位置 | 作用 |
|---|---|
| `SOUL.md` | 设计灵魂 + 血泪教训（必读） |
| `YuriArm/` | 固件 `firmware/esp32s3_exec/` + `yuriarm/` + `tools/leader_remote.py`（臂单控 CLI） |
| `YuriChassis/` | `car_remote.py` / `dual_remote.py`（无线 CLI）、`camera_car_drive.py`+GUI（有线相机车）、`kiwi_drive.py` |
| `YuriConsole/` | **遥控台 GUI**：`backend/{console_core,main,wired_car}.py` + `frontend/`（Vue3+Vite+Naive UI+Pinia）；`release/YuriConsole.exe` |
| `docs/gui-reference/` | MatsuriVoice 花信/祭主题参考源码（风格基线） |
| `docs/REMOTE_CONSOLE_REQ.md` | 遥控台需求 + 风格规范（U1 定稿） |

## 3. 环境事实（本机 2026-09）

- Python venv **在仓库根 `lerobot_venv312/`**（3.12.14 + lerobot 0.6.1 + pyserial + fastapi/uvicorn/pywebview/pyinstaller）。
  重建/装包见根 `ENVIRONMENT.md`（uv）。**python.exe 是 venvlauncher**，曾两次 0 字节损坏：
  修复 = 从 uv python `cpython-3.13.3-...\Lib\venv\scripts\nt\venvlauncher.exe` 复制改名。
- 串口：主动臂 COM7、ESP32 COM8(115200)、有线相机车默认 COM21(1M)。
- lerobot 源码在仓库外 editable（`pip show lerobot` 查位置）；旧 `E:\Anaconda\...` 是合作者 conda 示例，勿改、勿复制使用。
- 前端：`YuriConsole/frontend`（node 22；npm 用 `npm.cmd` 避免 ps1 执行策略）。改前端后 `npm run build` 才进生产/exe。
- 打包：`pyinstaller ... backend\main.py`（含 lerobot/torch ~200MB，release 走 **Git LFS**，.gitattributes 已 track）。
- 文档命令默认从**仓库根**执行；venv 相对路径 `..\lerobot_venv312\Scripts\python.exe`（子目录内）或 `lerobot_venv312\Scripts\...`（根）。

## 4. 运行方式

```bat
cd YuriConsole
..\lerobot_venv312\Scripts\python.exe backend\main.py --mock   :: mock 演示
:: 真机去掉 --mock；打包 exe 直接跑 release\YuriConsole.exe（frozen 默认开 pywebview 桌面壳）
```

CLI（无 GUI 版本存续，勿动）：
```bat
cd YuriChassis
..\lerobot_venv312\Scripts\python.exe dual_remote.py   :: 臂+轮无线双控
..\lerobot_venv312\Scripts\python.exe car_remote.py    :: 纯轮子
```

## 5. 硬性约束（沿用）

- 只用简体中文回复；术语保留英文；惜字如金；禁吹捧；不确定就说不确定，禁止编造。
- 写码前全局兼容检查；禁硬编码/临时逻辑；列技术债与回归风险；文档路径用相对。
- 禁止把机器绝对路径（`C:\Users\*`、`E:\Anaconda\...`、`~/lerobot` 等）写回文档/代码；历史 E 盘说明仅限 ENVIRONMENT/交接文档。
- git：s0lo201；标题 ≤50 字符祈使句；正文 what/why。
- 真机动作（烧录、驱动舵机）先经用户确认。
- 仓库大文件（YuriConsole/release/YuriConsole.exe 等）走 Git LFS，clone 需装 git-lfs。

## 6. 已知坑 / 技术债

- ESP32 只服务一个 TCP 客户端：重跑前先按 RESET 释放旧连接，否则反复重连。
- 重开 COM8 会复位 ESP32（boot 日志 ≠ 崩溃）。同一串口单进程。
- venv python.exe 0 字节：venvlauncher 修复（见上）。
- 手柄控机械臂 **pan/lift/elbow 方向符号是约定默认，未经真机确认**（可能需反向开关）。
- 手柄摇杆速度上限前端硬编码（同步 kiwi_drive 0.10/0.60，可改后端下发）。
- YuriConsole 真机全功能回归未做；D 视觉（YuriEye）未接入；B 脚本化 move_joints 步进未做。
- 从动臂/主动臂供电接触不良史：先查供电再查代码。夹爪 gripper raw [2045,3479] 勿改；estop_load=2000。
- `build/`、`dist/`、`*.spec`、`lerobot_venv312/`、`YuriEye/.venv/` 均已 gitignore；新增产物注意保持忽略。

## 7. 下一步候选（未定优先级）

1. YuriConsole 真机回归：无线小车手柄（X/Y/A/B/LB/RB）、右摇杆控臂三轴方向、夹爪、CameraCar 有线车。
2. 手柄控臂方向真机校准（或加反向开关）。
3. D 视觉区接 YuriEye（V1）。
4. B 区脚本化关节步进。
5. pywebview 壳 + 单 exe 全流程文档化（已有 exe 可参考 build 命令）。

> 新会话请复制 `docs/NEXT_SESSION_PROMPT.md` 作为起始提示词。

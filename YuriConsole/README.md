# Yuri 综合遥控台（YuriConsole）

> 需求与风格规范见 `docs/REMOTE_CONSOLE_REQ.md`（MatsuriVoice「花信/祭」双主题，U1 定稿）。
> 课程项目收尾版：A 连接与状态 / B 机械臂 / C 小车 / D 视觉占位 / E 安全与日志，
> F 有线相机小车独立页签；串口与主动臂口支持自动枚举下拉选择。
> 支持离线 mock 演示与真机连接（复用 YuriChassis/YuriArm 传输层，不绕过 SOUL 安全语义）。

有线相机车默认映射：`ID4=前中`、`ID5=后左`、`ID6=后右`；
方向为前中反向、后左反向、后右正向；前进时后左/后右同向、后退相反，前中轮保持 0 速。

## 结构

```
YuriConsole/
├── backend/
│   ├── console_core.py   # 核心：单写者 20Hz 主循环（bridge.step + car_drive + heartbeat）、mock、日志
│   └── main.py           # FastAPI + 静态托管 + pywebview 可选桌面壳
└── frontend/             # Vue3 + Vite + Naive UI + Pinia
    └── src/
        ├── theme.js      # 花信(浅)/祭(深) 主题令牌 -> naive themeOverrides + CSS 变量
        ├── stores/console.js   # Pinia：状态轮询 / 指令 API
        └── components/   # 六区面板 + 状态点
```

## 运行

### 生产（前端已 build）

```bat
cd YuriConsole
..\lerobot_venv312\Scripts\python.exe backend\main.py --mock
:: 自动开浏览器 http://127.0.0.1:8766 ；去 --mock 为真机模式
:: pywebview 桌面壳：加 --webview
```

### 开发（改前端热更新）

```bat
:: 终端1：后端（mock）
..\lerobot_venv312\Scripts\python.exe backend\main.py --mock --port 8766
:: 终端2：前端 vite dev（/api 代理到 8766）
cd frontend && npm run dev
```

改完前端执行 `npm run build` 让生产模式生效。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/state | 聚合状态（连接/急停/姿态/轮速） |
| GET | /api/gamepad/state | XInput 手柄状态（摇杆/按钮） |
| POST | /api/connect | {link: tcp\|serial, serial_port?, leader_port} |
| POST | /api/disconnect | 断开（0 速 + estop 收尾） |
| POST | /api/car/press | {key: w/a/s/d/z/x} 按住 |
| POST | /api/car/release | 松开 -> 0 速 |
| POST | /api/car/estop | 轮子急停（不动臂） |
| POST | /api/global/estop | 全局急停 |
| POST | /api/resume | 恢复 |
| POST | /api/arm/enabled | {enabled} 臂遥操作开关 |
| GET | /api/logs | 日志（?level=info\|warn\|error） |
| GET | /api/wired/ports | 有线相机车可用串口列表 |
| POST | /api/wired/connect | 连接有线相机车 {port?} |
| POST | /api/wired/disconnect | 断开有线相机车 |
| POST | /api/wired/press | {key} 键盘方向 |
| POST | /api/wired/release | 松开 -> 0 速 |
| POST | /api/wired/vel | 有线相机车摇杆速度 {vx, vy, omega} |
| POST | /api/wired/estop | 有线相机车急停 |
| GET | /api/serial/ports | 枚举本机可用串口（含 USB/蓝牙判定） |

## 收尾说明

- 已实现：A–F 六区、双主题、XInput 手柄、串口自动枚举、有线相机车 COM/键盘/手柄/连续速度；
  主动臂与 ESP32 串口从本机可用串口中自动选择（优先 USB 真串口）。
- 保持 CLI 兼容：脚本化 `move_joints` / 单关节步进仍走 `YuriArm` 命令行，GUI 不重复实现。
- 未纳入本课程范围：YuriEye 视觉面板实机接入、小车反向开关可视化（配置在
  `camera_car_drive` 标定文档中）、pywebview 壳真机实测。
- `YuriConsole.exe` 已发布至 `release/`，后端采用 pyinstaller，并随前端构建产物打包。
- naive-ui 全量引入，JS ~1.45MB（性能优化不在课程范围内）。

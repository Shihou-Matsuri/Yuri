# Yuri 综合遥控台（YuriConsole）

> 需求与风格规范见 `docs/REMOTE_CONSOLE_REQ.md`（MatsuriVoice「花信/祭」双主题，U1 定稿）。
> 当前为 **U2 MVP 骨架**：A 连接与状态 / B 机械臂 / C 小车 / D 视觉占位 / E 安全与日志，
> 支持离线 mock 演示与真机连接（复用 YuriChassis/YuriArm 传输层，不绕过 SOUL 安全语义）。

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
        └── components/   # 五区面板 + 状态点
```

## 运行

### 生产（前端已 build）

```bat
cd C:\Users\21209\Desktop\Yuri\YuriConsole
C:\Users\21209\Desktop\Yuri\lerobot_venv312\Scripts\python.exe backend\main.py --mock
:: 自动开浏览器 http://127.0.0.1:8766 ；去 --mock 为真机模式
:: pywebview 桌面壳：加 --webview
```

### 开发（改前端热更新）

```bat
:: 终端1：后端（mock）
C:\Users\21209\Desktop\Yuri\lerobot_venv312\Scripts\python.exe backend\main.py --mock --port 8766
:: 终端2：前端 vite dev（/api 代理到 8766）
cd frontend && npm run dev
```

改完前端执行 `npm run build` 让生产模式生效。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/state | 聚合状态（连接/急停/姿态/轮速） |
| POST | /api/connect | {link: tcp\|serial, serial_port?, leader_port} |
| POST | /api/disconnect | 断开（0 速 + estop 收尾） |
| POST | /api/car/press | {key: w/a/s/d/z/x} 按住 |
| POST | /api/car/release | 松开 -> 0 速 |
| POST | /api/car/estop | 轮子急停（不动臂） |
| POST | /api/global/estop | 全局急停 |
| POST | /api/resume | 恢复 |
| POST | /api/arm/enabled | {enabled} 臂遥操作开关 |
| GET | /api/logs | 日志（?level=info\|warn\|error） |

## 技术债 / 待办（U2 未完）

- 真机模式未经真机验证（结构复用 dual_remote，需实机回归）。
- D 视觉区为占位，YuriEye 接入未做（V1 里程碑）。
- B 区脚本化 move_joints / 单关节步进未做（保留 CLI）。
- 小车反向开关未接入（见 camera_car_drive 标定）。
- pywebview 壳未实测（需本机 WebView2 Runtime）。
- 单 exe 打包（pyinstaller 后端 + 前端产物）未做。
- naive-ui 全量引入，JS ~1.45MB（后续可按需引入优化）。
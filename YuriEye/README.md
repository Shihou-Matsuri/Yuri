# YuriEye：彩色立方体识别（罗技 C922）

基于罗技 C922 摄像头，实时识别**同尺寸（30mm）、不同颜色**的立方体，输出每个立方体的颜色与 2D 位置。
已采用 **YOLOv8m（ML：检测 + 颜色分类一体）** 路线；经典 HSV 基线保留作自动标注与无 GPU 降级方案。

## 现状（2026-08-27）

- 颜色：**红 / 黄 / 绿 / 蓝 / 橙 / 紫** 6 类
- 数据：`data/raw/` 282 张真实照片，**按类别分层划分** 173 训练 + 56 验证
- 模型：**YOLOv8m（25.8M 参数）**，mAP50 **0.949** / mAP50-95 **0.870**
- 权重：`ml/weights/best.pt`（gitignore，训练/同步后使用）

## 环境

| 用途 | 环境 | 说明 |
|---|---|---|
| ML（推荐） | `YuriEye/.venv` 或独立 uv env | Python 3.10 + torch cu128 + ultralytics，RTX 5070 Ti |
| CV 基线/标注 | 仓库根 `lerobot_venv312` | Python 3.12 + lerobot + OpenCV + numpy |

环境安装详见 [scripts/setup_env.md](scripts/setup_env.md)。

## 快速开始

```bash
# 1. 确认摄像头索引（本机罗技 C922 = 1）
python tools/list_cameras.py

# 2. ML 实时检测（yurieye 环境，推荐）
python tools/detect_ml.py                          # 实时窗口
python tools/detect_ml.py --image xx.jpg --json    # 单图 + JSON
python tools/detect_ml.py --conf 0.3               # 调置信度

# 3. CV 实时检测（lerobot 环境，降级/演示）
python tools/live_detect.py
python tools/live_detect.py --image examples/sample_cubes.png --json --no-show

# 4. 颜色标定（CV 用，GUI 点击采样）
python tools/calib_color.py

# 5. 采集真实数据（自动标注）
python tools/capture_dataset.py --count 100 --annotate --out data/raw

# 6. 已有照片批量自动标注
python tools/auto_label.py --src data/raw

# 7. 转 YOLO 格式 + 训练（yurieye 环境）
python ml/prepare_data.py --src data/raw --out data/yolo --val-ratio 0.2 --seed 42
python ml/train_yolo.py --data data/yolo/data.yaml --model yolov8m.pt --epochs 100 --batch 8 --name my_run
```

## 配置

`configs/default.json`：

- `camera`：索引、分辨率、曝光/白平衡（C922 支持手动锁定以稳定颜色）
- `cube`：真实边长 30mm、几何判据（面积/宽高比/solidity/顶点数）、形态学核尺寸
- `colors`：6 色 HSV 范围（已按实拍标定）与展示 RGB；类别顺序 = `colors` 键顺序（YOLO class id 与之对应）

## 目录结构

```
yurieye/     CV 核心库（camera / detector / geometry / color_utils / calib / visualize）
tools/       工具：list_cameras / live_detect(CV) / detect_ml(YOLO) / calib_color /
             calib_camera / capture_dataset / auto_label / make_sample
ml/          ML 管线：prepare_data(分层) / train_yolo / make_synthetic_dataset(可选) / README
configs/     配置（相机/几何/6 色 HSV）
examples/    合成示例图（6 色 9 块，随配置生成）
data/        数据（gitignore）：raw 照片 / yolo 数据集 / probe 中间产物
runs/, ml/weights/   训练产物与权重（gitignore）
docs/        方案设计文档
scripts/     环境安装说明
```

## 数据与模型（gitignore）

- `data/`、`runs/`、`ml/weights/`、`*.pt` 均不纳入 git，避免仓库膨胀与隐私问题
- 权重需在本机训练生成（`ml/train_yolo.py`）或另行同步

## 常见问题

- **摄像头打不开**：可能被其他应用（Windows 相机等）占用，关闭后重试；或确认 `configs/default.json` 的 `camera.index`
- **检测不到**：先确认光照与机位；ML 模型需要 `ml/weights/best.pt` 存在
- **颜色易混（红/橙）**：HSV 靠色相分离，红/橙在 H 上相邻；ML 已大幅缓解
- **小目标/多目标同框置信度低**：补充"小目标/密集"照片后重训
- **对接 YuriArm 抓取**：待确认；模型输出 bbox + 类别，可接抓取规划（需手眼标定）

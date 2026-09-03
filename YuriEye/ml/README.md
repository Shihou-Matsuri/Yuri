# YuriEye ML 路径（YOLO 检测 + 颜色分类）

经典 HSV 基线足够处理"同尺寸、不同颜色、光照稳定"的场景；ML 路径用于提升鲁棒性：
遮挡、杂乱背景、反光、颜色相近、小目标/密集目标时的稳定性。当前以 **YOLO 直接检测+分类** 为主。

## 当前结果（2026-08-27）

- 数据：`data/raw/` **282 张**真实照片（C922，1920x1080），自动标注 + 抽检
- 划分：`ml/prepare_data.py` **按类别分层**（每类都进验证集）→ 173 训练 + 56 验证
- 模型：**YOLOv8m（25,843,234 参数 ≈ 25.8M）**，640px，100 epochs，batch 8
- 指标：**mAP50 0.949 / mAP50-95 0.870**（P 0.876 / R 0.925）
- 各类 mAP50：red 0.99 / green 0.995 / purple 0.976 / orange 0.939 / yellow 0.924 / **blue 0.869（最弱）**
- 权重：`ml/weights/best.pt`（gitignore；`tools/detect_ml.py` 默认加载）

## 环境

推荐在独立 GPU venv 中训练（勿动仓库根 `lerobot_venv312` 的 CPU torch）：

```bash
uv venv .venv --python 3.10
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements.txt -r ml/requirements.txt
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"   # True
```

安装细节（镜像、轮子文件名坑）见 [scripts/setup_env.md](../scripts/setup_env.md)。

## 完整流程

```bash
# 1) 采集/放入真实照片到 data/raw（每色多块、不同角度/光照）
#    在线采集（自动标注）：python tools/capture_dataset.py --count 100 --annotate --out data/raw

# 2) 批量自动标注（已有照片）
python tools/auto_label.py --src data/raw
#    自动做了：色相 H 分离 + 暖色 S 下限排除肤色 + 分辨率自适应最小面积 + 顶部条带过滤
#    建议用 `data/probe/annotated*/` 渲染图抽检标注质量

# 3) 转 YOLO 格式（分层划分）
python ml/prepare_data.py --src data/raw --out data/yolo --val-ratio 0.2 --seed 42

# 4) 训练
python ml/train_yolo.py --data data/yolo/data.yaml --model yolov8m.pt \
    --epochs 100 --imgsz 640 --batch 8 --name my_run

# 5) 推理
python tools/detect_ml.py                          # 实时
python tools/detect_ml.py --image xx.jpg --json    # 单图
```

## 数据与标注说明

- 类别顺序 = `configs/default.json` 的 `colors` 键顺序（red, green, blue, orange, purple, yellow → id 0..5）
- 自动标注依赖 CV 基线的 HSV 标定；**新增光照/场景变化较大时建议重跑 `calib_color.py` 标定**
- 自动标注局限：肤色/键盘反光等误检已用过滤缓解，但复杂背景下仍需人工抽检
- 补数据建议：蓝/紫/黄实例偏少 → 每类 20+ 张、小目标与多目标同框 10+ 张

## 可选：合成数据兜底

```bash
python ml/make_synthetic_dataset.py --count 200 --out data/yolo --val-ratio 0.1
```

> 已修复生成器两个 bug（旋转坐标、先画后判重叠），生成质量经校验；真实数据充足时可不使用。

## 常见问题

- **pip 装 torch 失败**：PyPI 默认是 CPU 版；用上交/阿里云镜像下载 cu128 轮子并保持标准文件名，见 `scripts/setup_env.md`
- **验证集指标波动**：改用分层划分（`prepare_data.py --seed`）后指标稳定
- **某类 mAP 低**：该类样本少 → 补数据重训

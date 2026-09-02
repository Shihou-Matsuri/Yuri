# 环境设置

## 基线（经典 CV）

使用现有 `lerobot` conda 环境即可：

```bash
conda activate lerobot
python -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"
```

如换新环境：

```bash
conda create -n yurieye python=3.10
conda activate yurieye
pip install -r requirements.txt
```

## ML（YOLO）

本机 RTX 5070 Ti（Blackwell）需要 CUDA 12.8+ 的 PyTorch，使用独立环境 `yurieye`（已验证）：

```bash
conda create -n yurieye python=3.10 -y
conda activate yurieye
```

**PyTorch cu128（已验证流程）**：PyPI 默认是 CPU 版；直连 pytorch.org 大文件易断。
推荐从上交/阿里云 pytorch-wheels 镜像下载轮子后本地安装：

```bash
# 以 torch 2.11.0 / torchvision 0.26.0 为例（cp310 / win_amd64）
curl -L -C - -o %TEMP%\torch.whl ^
  "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/torch-2.11.0%2Bcu128-cp310-cp310-win_amd64.whl"
curl -L -o %TEMP%\torchvision.whl ^
  "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/torchvision-0.26.0%2Bcu128-cp310-cp310-win_amd64.whl"
# 注意：轮子文件名必须保持官方标准名（torch-2.11.0+cu128-...），否则 pip 拒绝安装
pip install %TEMP%\torch.whl %TEMP%\torchvision.whl
python -c "import torch; print(torch.cuda.is_available())"   # True
```

**ultralytics**（走清华 PyPI 镜像）：

```bash
pip install ultralytics -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> 注意：`lerobot` 环境里的 torch 是 CPU 版，不要在那里装 CUDA 版，避免破坏 LeRobot 依赖。

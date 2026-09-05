# 环境设置

## 仓库根 venv（推荐，可复现）

基线 CV 可直接使用仓库根 venv `lerobot_venv312/`（含 lerobot、OpenCV、numpy）；
安装/重建方式见仓库根 `ENVIRONMENT.md`：

```bash
..\lerobot_venv312\Scripts\python.exe -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"
```

ML（YOLO）需要 CUDA 12.8+ 的 PyTorch。若使用仓库根 uv 环境，可按需安装：

```bash
cd ..\..
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install -r YuriEye\requirements.txt -r YuriEye\ml\requirements.txt
```

旧机器曾有独立 conda 环境 `yurieye`（Python 3.10 + torch cu128）；这些是历史/合作者示例，
本仓库不再以机器绝对路径引用，推荐直接用上面的 uv 流程创建独立 GPU venv。

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

uv 场景等价命令：

```bash
uv pip install %TEMP%\torch.whl %TEMP%\torchvision.whl
```

**ultralytics**（走清华 PyPI 镜像）：

```bash
uv pip install ultralytics -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> 注意：仓库根 `lerobot_venv312` 若仅跑真机/LeRobot，不建议混装 CUDA torch；
> ML 训练建议独立 venv（如 `YuriEye\.venv`），避免破坏 LeRobot 依赖。

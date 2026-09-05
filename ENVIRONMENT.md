# 环境说明与重建（uv）

仓库统一使用根目录 `lerobot_venv312/`（Python 3.12）运行 Python/LeRobot 工具；
该目录已在 `.gitignore` 中，不入库。文档里出现的 `..\lerobot_venv312\Scripts\python.exe`
表示从子目录回到仓库根后调用；根目录下直接写 `.\lerobot_venv312\Scripts\python.exe`。

## 首次重建

```powershell
# 1) 安装 uv（若没有）: https://docs.astral.sh/uv/getting-started/installation/
uv --version

# 2) 在仓库根创建 3.12 venv（目录名固定，方便 bat/文档引用）
uv venv lerobot_venv312 --python 3.12

# 3) 安装 LeRobot 0.6.1（editable 源码可另行 pip show 确认）
uv pip install --python lerobot_venv312\Scripts\python.exe "lerobot[feetech]==0.6.1"

# 4) 常用附加依赖（已按本仓库用途收敛；可跳过其中不需要的）
uv pip install --python lerobot_venv312\Scripts\python.exe ^
  pyserial bleak fastapi "uvicorn[standard]" pywebview pyinstaller build123d matplotlib

# 5) 验证
lerobot_venv312\Scripts\python.exe -c "import lerobot, serial, cv2; print(lerobot.__version__)"
```

## 复现锁定版本

仓库根提供 `requirements.lock.txt`（由旧环境/上一轮验证产物导出的兼容版本，
含 PyTorch CPU 版）；需要完全复现时可：

```powershell
uv pip install --python lerobot_venv312\Scripts\python.exe -r requirements.lock.txt
```

> 锁文件用于“换机器快速恢复到已知可跑组合”。日常小工具无需逐项钉死，
> 直接按“首次重建”安装即可。

## 关于历史合作者 conda 环境

早期合作者曾在本地 `Anaconda/envs` 建 `lerobot`、`yurieye` 两个 conda 环境（仅存在于旧机）；
本仓库不复制、不引用机器绝对路径。保留 `requirements.lock.txt` 仅为导出参考，避免丢失已知组合。

## YuriEye ML（CUDA 12.8+）

仓库根环境默认保持 CPU torch，避免破坏 LeRobot。训练 YOLO 时在 `YuriEye/` 内建独立 venv：

```powershell
cd YuriEye
uv venv .venv --python 3.10
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements.txt -r ml\requirements.txt
```

详见 `YuriEye/scripts/setup_env.md` 与 `YuriEye/ml/README.md`。

## TLS/镜像问题

学校/公司网络若出现证书或 TLS 报错：

- 优先用 venv 自带 `pip`（走 Windows 系统证书）：`lerobot_venv312\Scripts\python.exe -m pip install ...`
- uv 可设 `UV_INSECURE_HOST` 仅限内部可信源，不推荐全局关闭校验
- PyPI 慢时可临时加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`

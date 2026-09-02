"""训练 YOLO 检测模型（需要 ultralytics 环境，见 ml/README.md）。

用法:
  python ml/train_yolo.py --data data/yolo/data.yaml --model yolov8n.pt --epochs 100 --imgsz 640
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/yolo/data.yaml")
    ap.add_argument("--model", default="yolov8n.pt")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--project", default="ml/runs")
    ap.add_argument("--name", default="train")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as e:
        print("未安装 ultralytics。请先创建 yurieye ML 环境并安装依赖：", file=sys.stderr)
        print("  conda create -n yurieye python=3.10 && conda activate yurieye", file=sys.stderr)
        print("  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128", file=sys.stderr)
        print("  pip install -r ml/requirements.txt", file=sys.stderr)
        raise SystemExit(1) from e

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"数据集配置不存在: {args.data}（先运行 ml/prepare_data.py）", file=sys.stderr)
        sys.exit(1)

    model = YOLO(args.model)
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
    )
    print(f"训练完成，权重在 {Path(args.project) / args.name / 'weights' / 'best.pt'}")


if __name__ == "__main__":
    main()

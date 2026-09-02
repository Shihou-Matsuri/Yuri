"""把采集数据整理为 YOLO 格式。

输入: data/raw/*.jpg + 同名 .json（capture_dataset.py --annotate 输出）
输出: data/yolo/{images,labels}/{train,val} + data.yaml
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yurieye.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--src", default="data/raw")
    ap.add_argument("--out", default="data/yolo")
    ap.add_argument("--val-ratio", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42, help="分层划分随机种子")
    args = ap.parse_args()

    cfg = load_config(args.config)
    labels = list(cfg.get("colors", {}).keys())
    if not labels:
        print("配置中没有 colors 键", file=sys.stderr)
        sys.exit(1)
    label_to_id = {name: i for i, name in enumerate(labels)}

    src = Path(args.src)
    out = Path(args.out)
    if not src.is_dir():
        print(f"源目录不存在: {src}", file=sys.stderr)
        sys.exit(1)

    images = sorted(p for p in src.iterdir() if p.suffix.lower() in IMG_EXTS)
    if not images:
        print(f"源目录没有图片: {src}", file=sys.stderr)
        sys.exit(1)

    valid = []
    for img_path in images:
        json_path = img_path.with_suffix(".json")
        if not json_path.exists():
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            dets = json.load(f)
        dets = [d for d in dets if d.get("label") in label_to_id]
        if not dets:
            continue
        valid.append((img_path, dets))

    if not valid:
        print("没有同时含图片与有效标注的样本", file=sys.stderr)
        sys.exit(1)

    # 清理旧输出，避免残留
    for sub in ("images", "labels", "data.yaml"):
        p = out / sub
        if p.is_dir():
            shutil.rmtree(p)
    (out / "images" / "train").mkdir(parents=True, exist_ok=True)
    (out / "images" / "val").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "val").mkdir(parents=True, exist_ok=True)

    # 按类别分层划分：每类都抽取 val_ratio 比例的样本进验证集，
    # 避免某类全部落在训练集导致验证指标失真。
    rng = __import__("random").Random(args.seed)
    val_set: set = set()
    for cls_id in range(len(labels)):
        cand = [img for img, dets in valid if any(d.get("label") == labels[cls_id] for d in dets)]
        rng.shuffle(cand)
        n = max(0, int(len(cand) * args.val_ratio))
        val_set.update(p.name for p in cand[:n])
    if not val_set:
        # 兜底：至少留 1 张做验证
        val_set.add(valid[0][0].name)
    train_names = [p.name for p, _ in valid if p.name not in val_set]
    if not train_names:
        print(f"警告: 样本数过少（{len(valid)}），训练集为空，YOLO 无法训练", file=sys.stderr)
    counts = {"train": 0, "val": 0}
    for img_path, dets in valid:
        split = "val" if img_path.name in val_set else "train"
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        out_img = out / "images" / split / img_path.name
        cv2.imwrite(str(out_img), img)

        lines = []
        for d in dets:
            x, y, bw, bh = d["bbox"]
            cx = (x + bw / 2) / w
            cy = (y + bh / 2) / h
            nw = bw / w
            nh = bh / h
            lines.append(f"{label_to_id[d['label']]} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
        label_path = out / "labels" / split / (img_path.stem + ".txt")
        label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts[split] += 1

    yaml_content = (
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        f"names:\n" + "".join(f"  {i}: {name}\n" for i, name in enumerate(labels))
    )
    (out / "data.yaml").write_text(yaml_content, encoding="utf-8")
    print(f"生成完成: train={counts['train']} val={counts['val']} 类别={labels}")
    print(f"数据集配置: {out / 'data.yaml'}")


if __name__ == "__main__":
    main()

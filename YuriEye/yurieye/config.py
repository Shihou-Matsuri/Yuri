"""配置加载与合并。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载 JSON 配置；文件不存在时返回空 dict（由调用方与默认值合并）。"""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)



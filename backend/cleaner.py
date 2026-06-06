"""
退出时缓存清理 — 保留核心索引，仅清空临时文件
"""

import shutil
from pathlib import Path


def cleanup_on_exit(cache_dir: Path) -> None:
    """清空临时缓存目录，保留 ChromaDB / SQLite / BM25 核心数据"""
    cache = Path(cache_dir)
    if cache.exists():
        try:
            shutil.rmtree(cache)
            cache.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

"""
退出时缓存清理
保留核心索引（ChromaDB / SQLite / BM25），仅清理临时文件。
"""

import shutil
from pathlib import Path


def cleanup_on_exit(cache_dir: Path) -> None:
    """
    仅清理临时缓存，保留核心索引数据。

    清理:
      - cache_dir/    临时缓存文件

    保留:
      - chroma_db/    向量索引
      - metadata.db   文件元数据
      - library/      硬链接文件
      - bm25_index.pkl BM25 索引
    """
    cache = Path(cache_dir)
    if cache.exists():
        try:
            shutil.rmtree(cache)
            cache.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

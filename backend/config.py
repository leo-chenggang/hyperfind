"""
HyperFind — 应用配置
- 平台自适应数据目录
- ONNX 模型路径解析（开发/打包双模式）
- 目录初始化与缓存清理
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional


def _data_home() -> Path:
    """平台对应的应用数据目录"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path.home() / ".local" / "share"
    return base / "HyperFind"


class AppConfig:
    """HyperFind 全局配置

    数据目录结构::

        ~/Library/Application Support/HyperFind/
        ├── library/          # 文件仓库（硬链接/软链接）
        │   ├── Excel/
        │   ├── Word/
        │   ├── PDF/
        │   ├── PowerPoint/
        │   ├── HTML/
        │   └── Markdown/
        ├── chroma_db/        # ChromaDB 持久化向量索引
        ├── metadata.db       # SQLite 元数据库
        ├── bm25_index.pkl    # BM25 序列化索引
        └── cache/            # 临时缓存（退出时清空）
    """

    FILE_TYPES = ("Excel", "Word", "PDF", "PowerPoint", "HTML", "Markdown")

    def __init__(self, data_home: Optional[Path] = None):
        self.data_home = data_home or _data_home()

        self.library_dir: Path = self.data_home / "library"
        self.db_path: Path = self.data_home / "metadata.db"
        self.chroma_dir: Path = self.data_home / "chroma_db"
        self.bm25_path: Path = self.data_home / "bm25_index.pkl"
        self.cache_dir: Path = self.data_home / "cache"
        self.model_dir: Path = self._resolve_model_dir()

    def _resolve_model_dir(self) -> Path:
        """解析 ONNX 模型目录

        优先级:
        1. 开发模式 — 项目根目录下的 models/multilingual-minilm/
        2. 打包模式 — 与可执行文件同级的 models/multilingual-minilm/
        """
        dev = Path(__file__).resolve().parent.parent / "models" / "multilingual-minilm"
        if dev.exists():
            return dev
        if getattr(sys, "frozen", False):
            bundle = Path(sys.executable).parent / "models" / "multilingual-minilm"
            if bundle.exists():
                return bundle
        return dev

    def ensure_dirs(self) -> None:
        """创建所有数据目录及子目录"""
        for d in (self.data_home, self.library_dir, self.cache_dir, self.chroma_dir):
            d.mkdir(parents=True, exist_ok=True)
        for ft in self.FILE_TYPES:
            (self.library_dir / ft).mkdir(parents=True, exist_ok=True)

    def clear_cache(self) -> None:
        """清空临时缓存（退出时调用，保留核心索引）"""
        try:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

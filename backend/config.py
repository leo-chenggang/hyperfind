"""
HyperFind 应用配置
管理数据目录、模型路径、缓存策略。
"""

import os
import sys
from pathlib import Path
from typing import Optional


def _get_data_home() -> Path:
    """获取平台对应的数据目录"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "HyperFind"


class AppConfig:
    """HyperFind 全局配置"""

    def __init__(self, data_home: Optional[Path] = None):
        self.data_home = data_home or _get_data_home()

        # 仓库目录 — 硬链接/软链接存储
        self.library_dir = self.data_home / "library"

        # 数据库文件
        self.db_path = self.data_home / "metadata.db"

        # ChromaDB 持久化路径
        self.chroma_dir = self.data_home / "chroma_db"

        # BM25 索引序列化路径
        self.bm25_path = self.data_home / "bm25_index.pkl"

        # 临时缓存 (退出时清空)
        self.cache_dir = self.data_home / "cache"

        # ONNX 模型路径
        self.model_dir = self._resolve_model_dir()

    def _resolve_model_dir(self) -> Path:
        """解析 ONNX 模型目录"""
        # 开发模式：项目根目录
        dev_path = Path(__file__).resolve().parent.parent / "models" / "multilingual-minilm"
        if dev_path.exists():
            return dev_path
        # 打包模式：与可执行文件同级 (PyInstaller)
        if getattr(sys, "frozen", False):
            bundle_path = Path(sys.executable).parent / "models" / "multilingual-minilm"
            if bundle_path.exists():
                return bundle_path
        return dev_path

    def ensure_dirs(self) -> None:
        """确保所有数据目录存在"""
        dirs = [
            self.data_home,
            self.library_dir,
            self.cache_dir,
            self.chroma_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # 创建文件类型子目录
        for ft in ("Excel", "Word", "PDF", "PowerPoint", "HTML", "Markdown"):
            (self.library_dir / ft).mkdir(parents=True, exist_ok=True)

    def clear_cache(self) -> None:
        """清空临时缓存（退出时调用）"""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)

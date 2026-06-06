"""
并发上传引擎 — 单线程顺序处理文件
编排: 链接 → 解析 → 切片 → 嵌入 → ChromaDB → BM25 → SQLite
全程推送进度事件到前端。

NOTE: 使用单线程顺序处理而非 ThreadPoolExecutor。
历史经验表明嵌套线程在 pywebview 打包环境下会引发崩溃。
顺序处理配合前端进度事件实时反馈，用户体验不变。
"""

import hashlib
import os
from pathlib import Path
from typing import Optional

from backend.config import AppConfig
from backend.database import Database
from backend.parsers.dispatcher import parse_file, detect_file_type
from backend.indexer.chunker import TextChunker
from backend.indexer.embedder import ONNXEmbedder
from backend.indexer.vector_store import VectorStore
from backend.indexer.bm25_store import BM25Store
from backend.upload.link_manager import link_file

CHUNK_SIZE = 512
CHUNK_OVERLAP = 128
EMBED_BATCH_SIZE = 32


class ConcurrentUploadEngine:
    """单线程顺序上传与索引引擎"""

    def __init__(self, config: AppConfig, db: Database, notify_callback=None):
        self.config = config
        self.db = db

        notify = notify_callback or (lambda e, d: None)
        self._notify = notify

        self._chunker = TextChunker(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP, min_chunk=10)
        self._embedder: Optional[ONNXEmbedder] = None
        self._vector_store: Optional[VectorStore] = None
        self._bm25_store: Optional[BM25Store] = None

    @property
    def embedder(self) -> ONNXEmbedder:
        if self._embedder is None:
            self._embedder = ONNXEmbedder(self.config.model_dir)
            try:
                self._embedder.load()
            except Exception:
                pass
        return self._embedder

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = VectorStore(self.config.chroma_dir)
            self._vector_store.initialize()
        return self._vector_store

    @property
    def bm25_store(self) -> BM25Store:
        if self._bm25_store is None:
            self._bm25_store = BM25Store()
            self._rebuild_bm25()
        return self._bm25_store

    def _rebuild_bm25(self) -> None:
        """从数据库重建 BM25 索引（应用启动时调用一次）"""
        try:
            all_file_ids = self.db.get_all_file_ids()
            corpus, chunk_ids = [], []
            for fid in all_file_ids:
                for c in self.db.get_chunks_by_file(fid):
                    corpus.append(c["content"])
                    chunk_ids.append(c["chunk_id"])
            if corpus:
                self._bm25_store.index(corpus, chunk_ids)
        except Exception:
            pass

    # ── 公共 API ────────────────────────────────────────

    def submit_files(self, file_paths: list[str]) -> dict:
        """提交文件上传（顺序阻塞处理，等待全部完成）

        返回: {"results": [{index, file_name, success, link_method, chunk_count, error?}, ...]}
        """
        results = []
        total = len(file_paths)
        for i, fp in enumerate(file_paths):
            path = Path(fp)
            try:
                r = self._process_one(path, i, total)
                results.append(r)
            except Exception as e:
                results.append({
                    "index": i, "file_name": path.name,
                    "success": False, "error": str(e),
                })
        return {"results": results}

    # ── 单文件处理（10 步 Pipeline）──────────────────────

    def _process_one(self, file_path: Path, index: int, total: int) -> dict:
        fname = file_path.name

        # Step 1: 计算 MD5
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "hashing", "progress": 0.05})
        file_hash = self._md5(file_path)
        if self.db.file_exists(file_hash):
            self._notify("file:progress", {
                "index": index, "file_name": fname, "status": "done",
                "progress": 1.0, "message": "文件已存在，跳过"})
            return {"index": index, "file_name": fname, "success": True, "status": "skipped"}

        # Step 2: 检测类型
        file_type = detect_file_type(file_path)
        if file_type is None:
            return {"index": index, "file_name": fname, "success": False,
                    "error": f"不支持的文件格式: {file_path.suffix}"}

        # Step 3: 链接到仓库
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "linking", "progress": 0.1})
        ext = file_path.suffix.lower()
        lib_dir = Path(str(self.config.library_dir))
        lib_dest = lib_dir / file_type.capitalize() / fname
        link_method = link_file(file_path, lib_dest)

        # Step 4: 解析
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "parsing", "progress": 0.2})
        raw_chunks = parse_file(file_path)
        if not raw_chunks:
            return {"index": index, "file_name": fname, "success": False,
                    "error": "文件解析无内容"}

        # Step 5: 切片
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "chunking", "progress": 0.3})
        chunks = self._chunker.chunk_documents(raw_chunks)
        if not chunks:
            return {"index": index, "file_name": fname, "success": False,
                    "error": "文本切片后无内容"}

        # Step 6: 嵌入
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "embedding", "progress": 0.4})
        embedder_ok = self.embedder.is_loaded
        chunk_texts = [c["content"] for c in chunks]
        chunk_ids = [f"{file_hash}_{i}" for i in range(len(chunks))]
        embeddings = None
        if embedder_ok:
            embeddings = self.embedder.encode(chunk_texts, batch_size=EMBED_BATCH_SIZE)

        # Step 7: ChromaDB 存储
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "saving", "progress": 0.7})
        if embedder_ok and embeddings is not None and len(embeddings) > 0:
            metadatas = [{
                "file_id": file_hash,
                "file_name": fname,
                "file_type": file_type,
                "chunk_index": i,
                "char_offset": chunks[i]["char_offset"],
            } for i in range(len(chunks))]
            self.vector_store.add_vectors(chunk_ids, embeddings, chunk_texts, metadatas)

        # Step 8: BM25 索引
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "indexing", "progress": 0.85})
        self.bm25_store.update(chunk_texts, chunk_ids)

        # Step 9: SQLite 写入
        file_size = file_path.stat().st_size
        self.db.add_file(
            file_id=file_hash,
            original_path=str(file_path),
            library_path=str(lib_dest),
            link_method=link_method,
            file_name=fname,
            file_type=file_type,
            file_ext=ext,
            file_size=file_size,
            chunk_count=len(chunks),
        )
        db_chunks = [{
            "chunk_id": f"{file_hash}_{i}",
            "file_id": file_hash,
            "chunk_index": i,
            "content": chunks[i]["content"],
            "char_offset": chunks[i]["char_offset"],
        } for i in range(len(chunks))]
        self.db.add_chunks(db_chunks)

        # Step 10: 完成
        self._notify("file:progress", {
            "index": index, "file_name": fname, "status": "done", "progress": 1.0,
            "link_method": link_method, "chunk_count": len(chunks)})
        self._notify("file:uploaded", {
            "file_id": file_hash, "file_name": fname, "file_type": file_type})

        return {
            "index": index, "file_name": fname, "success": True,
            "link_method": link_method, "chunk_count": len(chunks),
        }

    @staticmethod
    def _md5(file_path: Path) -> str:
        """计算文件 MD5 哈希"""
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

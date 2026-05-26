"""
并发上传引擎 — 10 线程并行处理文件
编排: 链接 → 解析 → 切片 → 嵌入 → BM25 → ChromaDB → SQLite
全程推送进度事件到前端
"""

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from backend.config import AppConfig
from backend.database import Database
from backend.parsers.dispatcher import parse_file, detect_file_type, FormatDispatchError
from backend.indexer.chunker import TextChunker
from backend.indexer.embedder import ONNXEmbedder
from backend.indexer.vector_store import VectorStore
from backend.indexer.bm25_store import BM25Store
from backend.upload.link_manager import link_file

MAX_WORKERS = min(10, os.cpu_count() or 4)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 128
EMBED_BATCH_SIZE = 32


class ConcurrentUploadEngine:
    """并发文件上传与索引引擎"""

    def __init__(self, config: AppConfig, db: Database, notify_callback=None):
        self.config = config
        self.db = db
        self._notify = notify_callback or (lambda e, d: None)
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self._bm25_lock = threading.Lock()

        # 组件 (延迟初始化)
        self._embedder: Optional[ONNXEmbedder] = None
        self._vector_store: Optional[VectorStore] = None
        self._bm25_store: Optional[BM25Store] = None
        self._chunker = TextChunker(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP, min_chunk=10)

        # 上传任务追踪 (非阻塞模式)
        self._tasks: dict = {}
        self._tasks_lock = threading.Lock()

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = ONNXEmbedder(self.config.model_dir)
            try:
                self._embedder.load()
            except Exception:
                pass
        return self._embedder

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = VectorStore(self.config.chroma_dir)
            self._vector_store.initialize()
        return self._vector_store

    @property
    def bm25_store(self):
        if self._bm25_store is None:
            self._bm25_store = BM25Store()
            # 从数据库恢复已有索引
            self._rebuild_bm25()
        return self._bm25_store

    def _rebuild_bm25(self):
        """从数据库重建 BM25 索引"""
        try:
            all_files = self.db.get_all_file_ids()
            corpus = []
            chunk_ids = []
            for fid in all_files:
                chunks = self.db.get_chunks_by_file(fid)
                for c in chunks:
                    corpus.append(c["content"])
                    chunk_ids.append(c["chunk_id"])
            if corpus:
                self._bm25_store.index(corpus, chunk_ids)
        except Exception:
            pass

    # ── 公共 API ────────────────────────────────────────

    def submit_files(self, file_paths: list[str]) -> dict:
        """
        提交文件上传（阻塞模式 — 等待所有文件处理完成）。

        返回: {"results": [{index, file_name, success, link_method, chunk_count, error?}, ...]}
        """
        paths = [Path(p) for p in file_paths]
        total = len(paths)
        results_map = {}

        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total)) as executor:
            futures = {
                executor.submit(self._process_one, p, i, total): i
                for i, p in enumerate(paths)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results_map[idx] = future.result()
                except Exception as e:
                    results_map[idx] = {
                        "index": idx, "file_name": paths[idx].name,
                        "success": False, "error": str(e),
                    }

        # 按原始顺序排列
        return {"results": [results_map[i] for i in range(total)]}

    # ── 单文件处理 ──────────────────────────────────────

    def _process_one(self, file_path: Path, index: int, total: int) -> dict:
        """处理单个文件：链接→解析→切片→嵌入→索引→存储"""
        file_name = file_path.name

        try:
            # ── Step 1: MD5 去重 ──
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "linking", "progress": 0.0,
            })
            file_hash = self._md5(file_path)

            if self.db.file_exists(file_hash):
                return {
                    "index": index, "file_name": file_name,
                    "success": True, "status": "skipped",
                    "message": "文件已存在，跳过",
                }

            # ── Step 2: 检测文件类型 ──
            file_type = detect_file_type(file_path)
            if file_type is None:
                return {
                    "index": index, "file_name": file_name,
                    "success": False,
                    "error": f"不支持的文件格式: {file_path.suffix}",
                }

            # ── Step 3: 硬链接到仓库 ──
            ext = file_path.suffix.lower()
            lib_dir = self.config.library_dir
            # 用原始 Path 引用
            lib_dest = Path(str(lib_dir)) / file_type.capitalize() / file_name
            link_method = link_file(file_path, lib_dest)

            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "linking", "progress": 0.1,
            })

            # ── Step 4: 解析文件 ──
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "parsing", "progress": 0.2,
            })
            raw_chunks = parse_file(file_path)
            if not raw_chunks:
                return {
                    "index": index, "file_name": file_name,
                    "success": False,
                    "error": "文件解析无内容",
                }

            # ── Step 5: 文本切片 ──
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "chunking", "progress": 0.3,
            })
            chunks = self._chunker.chunk_documents(raw_chunks)
            if not chunks:
                return {
                    "index": index, "file_name": file_name,
                    "success": False,
                    "error": "文本切片后无内容（文件可能太短）",
                }

            # ── Step 6: ONNX 嵌入 ──
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "embedding", "progress": 0.4,
            })

            embedder_ok = self.embedder.is_loaded
            chunk_texts = [c["content"] for c in chunks]
            chunk_ids = [f"{file_hash}_{i}" for i in range(len(chunks))]

            if embedder_ok:
                embeddings = self.embedder.encode(chunk_texts, batch_size=EMBED_BATCH_SIZE)
            else:
                embeddings = None

            # ── Step 7: ChromaDB 存储 ──
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "saving", "progress": 0.7,
            })

            if embedder_ok and embeddings is not None and len(embeddings) > 0:
                metadatas = [
                    {
                        "file_id": file_hash,
                        "file_name": file_name,
                        "file_type": file_type,
                        "chunk_index": i,
                        "char_offset": chunks[i]["char_offset"],
                    }
                    for i in range(len(chunks))
                ]
                self.vector_store.add_vectors(chunk_ids, embeddings, chunk_texts, metadatas)

            # ── Step 8: BM25 索引 ──
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "indexing", "progress": 0.85,
            })
            with self._bm25_lock:
                self.bm25_store.update(chunk_texts, chunk_ids)

            # ── Step 9: SQLite 写入 ──
            file_size = file_path.stat().st_size
            self.db.add_file(
                file_id=file_hash,
                original_path=str(file_path),
                library_path=str(lib_dest),
                link_method=link_method,
                file_name=file_name,
                file_type=file_type,
                file_ext=ext,
                file_size=file_size,
                chunk_count=len(chunks),
            )

            db_chunks = [
                {
                    "chunk_id": f"{file_hash}_{i}",
                    "file_id": file_hash,
                    "chunk_index": i,
                    "content": chunks[i]["content"],
                    "char_offset": chunks[i]["char_offset"],
                }
                for i in range(len(chunks))
            ]
            self.db.add_chunks(db_chunks)

            # ── Step 10: 完成 ──
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "done", "progress": 1.0,
                "link_method": link_method,
                "chunk_count": len(chunks),
            })
            self._notify("file:uploaded", {
                "file_id": file_hash,
                "file_name": file_name,
                "file_type": file_type,
            })

            return {
                "index": index,
                "file_name": file_name,
                "success": True,
                "link_method": link_method,
                "chunk_count": len(chunks),
            }

        except Exception as e:
            self._notify("file:progress", {
                "index": index, "file_name": file_name,
                "status": "error", "progress": 0,
                "error": str(e),
            })
            return {
                "index": index,
                "file_name": file_name,
                "success": False,
                "error": str(e),
            }

    # ── 工具方法 ────────────────────────────────────────

    @staticmethod
    def _md5(file_path: Path) -> str:
        """计算文件 MD5"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

"""
HyperFind 混合搜索引擎
BM25 (bm25s + jieba) + 向量 (ONNX + ChromaDB) + RRF 融合 + 三段过滤

NOTE: BM25 索引采用延迟重建策略。上传时不重建，首次搜索时一次性构建。
"""

import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from backend.database import Database

if TYPE_CHECKING:
    from backend.upload.engine import ConcurrentUploadEngine

MAX_VECTOR_DISTANCE = 1.2
MIN_BM25_SCORE = 0.0
MIN_RRF_SCORE = 0.01
RRF_K = 60


class HybridSearchEngine:
    """BM25 + 向量 + RRF 混合搜索引擎

    接收 upload_engine 引用，按需访问其内嵌的 embedder/vector_store/bm25_store。
    首次搜索时自动触发 BM25 延迟重建。
    """

    def __init__(self, db: Database, upload_engine: "ConcurrentUploadEngine"):
        self.db = db
        self._engine = upload_engine

    @property
    def embedder(self):
        return self._engine.embedder

    @property
    def vector_store(self):
        return self._engine.vector_store

    @property
    def bm25_store(self):
        return self._engine.bm25_store

    def search(
        self,
        query: str,
        file_type_filter: str = "all",
        search_mode: str = "hybrid",
    ) -> dict:
        t0 = time.perf_counter()

        # Step 0: 延迟重建 BM25（首次搜索时触发）
        if search_mode in ("hybrid", "keyword"):
            self._engine.ensure_bm25_ready()

        # Step 1: BM25 关键词搜索
        bm25_results = []
        if search_mode in ("hybrid", "keyword"):
            bm25_results = self.bm25_store.search(query, k=30)

        # Step 2: 向量语义搜索
        vector_results = []
        if search_mode in ("hybrid", "semantic") and self.embedder.is_loaded:
            query_vec = self.embedder.encode([query])
            where = {"file_type": file_type_filter} if file_type_filter != "all" else None
            chroma_raw = self.vector_store.query(query_vec, n_results=30, where=where)

            ids = chroma_raw.get("ids", [[]])[0]
            distances = chroma_raw.get("distances", [[]])[0]
            metadatas = chroma_raw.get("metadatas", [[]])[0]

            for i, chunk_id in enumerate(ids):
                distance = distances[i]
                if distance > MAX_VECTOR_DISTANCE:
                    continue
                meta = metadatas[i] or {}
                vector_results.append({
                    "chunk_id": chunk_id,
                    "score": 1.0 - distance / 2.0,
                    "file_id": meta.get("file_id", ""),
                    "file_type": meta.get("file_type", ""),
                })

        # Step 3: RRF 融合
        if search_mode == "hybrid":
            fused = self._rrf_fusion(vector_results, bm25_results)
        elif search_mode == "keyword":
            fused = [(r["chunk_id"], r["score"]) for r in bm25_results]
        else:
            fused = [(r["chunk_id"], r["score"]) for r in vector_results]

        # Step 4: RRF 阈值过滤（仅混合模式）
        matched = []
        for chunk_id, score in fused:
            if search_mode == "hybrid" and score < MIN_RRF_SCORE:
                continue
            matched.append((chunk_id, score))

        # Step 5: 按 file_id 分组
        grouped = self._group_by_file(matched, bm25_results, vector_results)

        # Step 6: 文件类型过滤
        if file_type_filter != "all":
            grouped = [g for g in grouped if g["file_type"] == file_type_filter]

        t1 = time.perf_counter()
        return {
            "query": query,
            "total_files": len(grouped),
            "total_hits": sum(g["match_count"] for g in grouped),
            "search_time_ms": int((t1 - t0) * 1000),
            "results": grouped,
        }

    @staticmethod
    def _rrf_fusion(
        vector_results: list[dict],
        bm25_results: list[dict],
        k: int = RRF_K,
    ) -> list[tuple[str, float]]:
        scores: dict[str, float] = {}
        for rank, r in enumerate(vector_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        for rank, r in enumerate(bm25_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def _group_by_file(
        self,
        matched: list[tuple[str, float]],
        bm25_results: list[dict],
        vector_results: list[dict],
    ) -> list[dict]:
        chunk_index: dict[str, str] = {}
        for r in bm25_results + vector_results:
            cid = r["chunk_id"]
            if cid not in chunk_index:
                chunk_index[cid] = r.get("file_id", cid.rsplit("_", 1)[0])

        file_groups: dict[str, list[tuple[str, float]]] = {}
        for chunk_id, rrf_score in matched:
            fid = chunk_index.get(chunk_id, chunk_id.rsplit("_", 1)[0])
            file_groups.setdefault(fid, []).append((chunk_id, rrf_score))

        results = []
        for fid, chunk_pairs in file_groups.items():
            file = self.db.get_file(fid)
            if not file:
                continue

            all_chunks = {c["chunk_id"]: c for c in self.db.get_chunks_by_file(fid)}

            snippets = []
            for chunk_id, score in sorted(chunk_pairs, key=lambda x: x[1], reverse=True):
                chunk = all_chunks.get(chunk_id)
                if chunk:
                    snippets.append({
                        "chunk_id": chunk_id,
                        "content": chunk["content"],
                        "char_offset": chunk["char_offset"],
                        "score": round(score, 4),
                    })

            if not snippets:
                continue

            results.append({
                "file_id": fid,
                "file_name": file["file_name"],
                "file_type": file["file_type"],
                "file_path": file["original_path"],
                "library_path": file["library_path"],
                "match_count": len(snippets),
                "snippets": snippets,
            })

        return sorted(results, key=lambda x: x["match_count"], reverse=True)

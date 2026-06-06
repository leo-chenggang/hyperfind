"""
HyperFind 混合搜索引擎
BM25 (bm25s + jieba) + 向量 (ONNX + ChromaDB) + RRF 融合 + 三段过滤
"""

import time
from pathlib import Path
from typing import Optional

from backend.database import Database
from backend.indexer.embedder import ONNXEmbedder
from backend.indexer.vector_store import VectorStore
from backend.indexer.bm25_store import BM25Store

MAX_VECTOR_DISTANCE = 1.2
MIN_BM25_SCORE = 0.0
MIN_RRF_SCORE = 0.01
RRF_K = 60


class HybridSearchEngine:
    """BM25 + 向量 + RRF 混合搜索引擎"""

    def __init__(
        self,
        db: Database,
        embedder: ONNXEmbedder,
        vector_store: VectorStore,
        bm25_store: BM25Store,
    ):
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.bm25_store = bm25_store

    def search(
        self,
        query: str,
        file_type_filter: str = "all",
        search_mode: str = "hybrid",
    ) -> dict:
        t0 = time.perf_counter()

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

        # Step 5: 按 file_id 分组（修复 N+1 — 每个文件只查一次 DB）
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
        # chunk_id → file_id 索引
        chunk_index: dict[str, str] = {}
        for r in bm25_results + vector_results:
            cid = r["chunk_id"]
            if cid not in chunk_index:
                chunk_index[cid] = r.get("file_id", cid.rsplit("_", 1)[0])

        # 按 file_id 分组 (chunk_id, rrf_score)
        file_groups: dict[str, list[tuple[str, float]]] = {}
        for chunk_id, rrf_score in matched:
            fid = chunk_index.get(chunk_id, chunk_id.rsplit("_", 1)[0])
            file_groups.setdefault(fid, []).append((chunk_id, rrf_score))

        results = []
        for fid, chunk_pairs in file_groups.items():
            file = self.db.get_file(fid)
            if not file:
                continue

            # 一次查询该文件的所有 chunks（修复原 N+1 问题）
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

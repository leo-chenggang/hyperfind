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

# ── 三段过滤阈值 ──
MAX_VECTOR_DISTANCE = 1.2    # ChromaDB 余弦距离 (0=完全相同, 2=完全相反)
MIN_BM25_SCORE = 0.0         # BM25 最小分数
MIN_RRF_SCORE = 0.01         # RRF 融合后最低分数


class HybridSearchEngine:
    """BM25 + 向量 + RRF 混合搜索引擎"""

    def __init__(self, db: Database, embedder: ONNXEmbedder,
                 vector_store: VectorStore, bm25_store: BM25Store):
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.bm25_store = bm25_store

    # ── 公共 API ──────────────────────────────────────────

    def search(
        self,
        query: str,
        file_type_filter: str = "all",
        search_mode: str = "hybrid",
    ) -> dict:
        """
        执行混合搜索。

        Returns:
            {
                "query": str,
                "total_files": int,
                "total_hits": int,
                "search_time_ms": int,
                "results": [{file_id, file_name, file_type, file_path,
                             library_path, match_count, snippets: [...]}]
            }
        """
        t0 = time.perf_counter()

        # ── Step 1: BM25 关键词搜索 ──
        bm25_results = []
        if search_mode in ("hybrid", "keyword"):
            bm25_results = self.bm25_store.search(query, k=30)

        # ── Step 2: 向量语义搜索 ──
        vector_results = []
        if search_mode in ("hybrid", "semantic"):
            if self.embedder.is_loaded:
                query_vec = self.embedder.encode([query])
                where = None
                if file_type_filter != "all":
                    where = {"file_type": file_type_filter}
                chroma_raw = self.vector_store.query(query_vec, n_results=30, where=where)
                # 转换为统一格式
                for i in range(len(chroma_raw.get("ids", [[]])[0])):
                    chunk_id = chroma_raw["ids"][0][i]
                    distance = chroma_raw["distances"][0][i]
                    meta = chroma_raw.get("metadatas", [[]])[0][i] or {}
                    # 三段过滤①: 向量距离
                    if distance > MAX_VECTOR_DISTANCE:
                        continue
                    vector_results.append({
                        "chunk_id": chunk_id,
                        "score": 1.0 - distance / 2.0,
                        "file_id": meta.get("file_id", ""),
                        "file_type": meta.get("file_type", ""),
                    })

        # ── Step 3: RRF 融合 ──
        if search_mode == "hybrid":
            fused = self._rrf_fusion(vector_results, bm25_results)
        elif search_mode == "keyword":
            fused = [(r["chunk_id"], r["score"]) for r in bm25_results]
        else:  # semantic
            fused = [(r["chunk_id"], r["score"]) for r in vector_results]

        # ── Step 4: 三段过滤③ (RRF 分数，仅混合模式) ──
        matched_chunks = []
        for chunk_id, score in fused:
            if search_mode == "hybrid" and score < MIN_RRF_SCORE:
                continue
            matched_chunks.append((chunk_id, score))

        # ── Step 5: 按 file_id 分组 + 提取摘要 ──
        grouped = self._group_by_file(matched_chunks, bm25_results, vector_results)

        # ── Step 6: 文件类型过滤 ──
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

    # ── RRF 融合 ─────────────────────────────────────────

    @staticmethod
    def _rrf_fusion(
        vector_results: list[dict],
        bm25_results: list[dict],
        k: int = 60,
    ) -> list[tuple[str, float]]:
        """
        Reciprocal Rank Fusion (Cormack et al. 2009).
        score[d] = Σ 1/(k + rank + 1) for each ranked list.
        """
        scores = {}
        for rank, r in enumerate(vector_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        for rank, r in enumerate(bm25_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # ── 结果分组 ─────────────────────────────────────────

    def _group_by_file(
        self,
        matched: list[tuple[str, float]],
        bm25_results: list[dict],
        vector_results: list[dict],
    ) -> list[dict]:
        """按 file_id 分组，提取内容摘要"""
        # 构建 chunk_id → {file_id} 索引
        chunk_index = {}
        for r in bm25_results + vector_results:
            cid = r["chunk_id"]
            if cid not in chunk_index:
                chunk_index[cid] = {"file_id": r.get("file_id", cid.rsplit("_", 1)[0])}

        # 按 file_id 分组
        file_groups = {}
        for chunk_id, rrf_score in matched:
            fid = chunk_index.get(chunk_id, {}).get("file_id", chunk_id.rsplit("_", 1)[0])
            if fid not in file_groups:
                file_groups[fid] = []
            file_groups[fid].append((chunk_id, rrf_score))

        # 组装每个文件的结果
        results = []
        for fid, chunk_pairs in file_groups.items():
            file = self.db.get_file(fid)
            if not file:
                continue

            snippets = []
            for chunk_id, score in sorted(chunk_pairs, key=lambda x: x[1], reverse=True):
                chunks = self.db.get_chunks_by_file(fid)
                for c in chunks:
                    if c["chunk_id"] == chunk_id:
                        snippets.append({
                            "chunk_id": chunk_id,
                            "content": c["content"],
                            "char_offset": c["char_offset"],
                            "score": round(score, 4),
                        })
                        break

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

        # 按匹配数量降序
        return sorted(results, key=lambda x: x["match_count"], reverse=True)

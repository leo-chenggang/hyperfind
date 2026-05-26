"""
BM25 关键词搜索引擎
bm25s + jieba 中文分词 + 线程安全锁
"""

import threading
from pathlib import Path
from typing import Optional


class BM25Store:
    """BM25 全文搜索索引"""

    def __init__(self, index_path: Optional[Path] = None):
        self._corpus: list[str] = []
        self._chunk_ids: list[str] = []
        self._retriever: Optional[object] = None
        self._indexed: bool = False
        self._index_path = index_path
        self._lock = threading.Lock()

    def _get_stopwords(self) -> set:
        """中文停用词"""
        return {"的", "了", "在", "是", "我", "有", "和", "就",
                "不", "人", "都", "一", "一个", "上", "也", "很",
                "到", "说", "要", "去", "你", "会", "着", "没有",
                "看", "好", "自己", "这", "他", "她", "它", "们",
                "那", "些", "所", "为", "所以", "因为", "但是",
                "可以", "这个", "那个", "什么", "怎么", "如何"}

    def index(self, corpus: list[str], chunk_ids: list[str]) -> None:
        """
        构建 BM25 索引。

        Args:
            corpus: 文本列表
            chunk_ids: 对应的 chunk_id 列表
        """
        import jieba
        import bm25s

        with self._lock:
            self._corpus = corpus
            self._chunk_ids = chunk_ids

            if not corpus:
                self._retriever = None
                self._indexed = False
                return

            stopwords = self._get_stopwords()
            tokenized = [
                " ".join([t for t in jieba.cut(text) if len(t) > 1 and t not in stopwords])
                for text in corpus
            ]

            self._retriever = bm25s.BM25()
            self._retriever.index(tokenized)
            self._indexed = True

    def update(self, new_texts: list[str], new_chunk_ids: list[str]) -> None:
        """增量更新索引 — 追加新文本"""
        combined_texts = self._corpus + new_texts
        combined_ids = self._chunk_ids + new_chunk_ids
        self.index(combined_texts, combined_ids)

    def remove_by_prefix(self, file_id: str) -> None:
        """移除指定 file_id 的所有文本块"""
        with self._lock:
            keep_texts = []
            keep_ids = []
            for tid, text in zip(self._chunk_ids, self._corpus):
                if not tid.startswith(file_id):
                    keep_ids.append(tid)
                    keep_texts.append(text)
            self.index(keep_texts, keep_ids)

    def search(self, query: str, k: int = 20) -> list[dict]:
        """
        搜索 BM25 索引。

        返回: [{"chunk_id": str, "score": float}, ...]
        """
        import jieba
        import bm25s

        with self._lock:
            if not self._indexed or not self._retriever or not self._corpus:
                return []

            k = min(k, len(self._corpus))
            if k == 0:
                return []

            stopwords = self._get_stopwords()
            tokens = [t for t in jieba.cut(query) if len(t) > 1 and t not in stopwords]
            if not tokens:
                return []

            query_tokenized = bm25s.tokenize([" ".join(tokens)], stopwords="en", stemmer=None)

            try:
                results, scores = self._retriever.retrieve(query_tokenized, k=k)
            except Exception:
                return []

            output = []
            for doc_idx, score in zip(results[0], scores[0]):
                idx = int(doc_idx)
                output.append({
                    "chunk_id": self._chunk_ids[idx],
                    "score": float(score),
                })

            return output

    @property
    def size(self) -> int:
        return len(self._corpus)

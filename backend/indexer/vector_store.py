"""
ChromaDB 向量存储封装
持久化向量索引, HNSW + 余弦相似度
"""

import os
from pathlib import Path
from typing import Optional

# 禁用 ChromaDB 遥测（离线应用不需要）
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.config import Settings


def _get_np():
    import numpy
    return numpy


class VectorStore:
    """ChromaDB 向量存储"""

    COLLECTION_NAME = "hyperfind_docs"
    HNSW_CONFIG = {
        "hnsw:space": "cosine",
        "hnsw:construction_ef": 200,
        "hnsw:search_ef": 100,
        "hnsw:M": 16,
    }

    def __init__(self, persist_dir: Path):
        self.persist_dir = Path(persist_dir)
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[object] = None

    def initialize(self) -> None:
        """初始化 ChromaDB 客户端和 collection"""
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata=self.HNSW_CONFIG,
        )

    @property
    def client(self):
        if self._client is None:
            self.initialize()
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self.initialize()
        return self._collection

    def add_vectors(
        self,
        ids: list[str],
        embeddings,  # numpy array (n, 384) → list of list
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """批量添加向量到 ChromaDB"""
        np = _get_np()
        # ChromaDB 需要原生 Python list — 用 tolist()
        emb_list = embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
        self.collection.add(
            ids=ids,
            embeddings=emb_list,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding,  # numpy array (1, 384) or list
        n_results: int = 20,
        where: Optional[dict] = None,
    ) -> dict:
        """
        查询最相似的向量。

        返回 ChromaDB 原始结果:
        {
            "ids": [[...]],
            "distances": [[...]],
            "metadatas": [[...]],
            "documents": [[...]],
        }
        """
        np = _get_np()
        # ChromaDB 需要原生 Python float — 必须用 .tolist()
        if hasattr(query_embedding, "tolist"):
            vec = query_embedding.tolist()
        elif isinstance(query_embedding, list):
            vec = query_embedding
        else:
            vec = list(query_embedding)

        # 处理 2D 数组 (如 embs[0:1]) — 取第一行
        if vec and isinstance(vec[0], list):
            vec = vec[0]

        # 确保是 float 列表
        vec = [float(v) for v in vec]

        # Clamp n_results
        count = self.collection.count()
        if count == 0:
            return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}
        n = min(n_results, count)

        kwargs = {"query_embeddings": [vec], "n_results": n}
        if where:
            kwargs["where"] = where

        return self.collection.query(**kwargs)

    def delete_by_file_id(self, file_id: str) -> None:
        """删除指定文件的所有向量"""
        self.collection.delete(where={"file_id": file_id})

    def clear_all(self) -> None:
        """清空所有向量"""
        if self._client:
            self._client.delete_collection(self.COLLECTION_NAME)
            self._collection = None

    def count(self) -> int:
        """返回向量总数"""
        return self.collection.count()

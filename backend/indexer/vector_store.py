"""
ChromaDB 向量存储封装
HNSW + 余弦相似度。完全离线，遥测已禁用。
"""

import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.config import Settings


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
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
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
        embeddings,
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """批量添加向量到 ChromaDB"""
        emb_list = embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
        self.collection.add(
            ids=ids,
            embeddings=emb_list,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding,
        n_results: int = 30,
        where: Optional[dict] = None,
    ) -> dict:
        """查询最相似的向量

        返回 ChromaDB 原始结果:
        {"ids": [[...]], "distances": [[...]], "metadatas": [[...]], "documents": [[...]]}
        """
        if hasattr(query_embedding, "tolist"):
            vec = query_embedding.tolist()
        elif isinstance(query_embedding, list):
            vec = query_embedding
        else:
            vec = list(query_embedding)

        if vec and isinstance(vec[0], list):
            vec = vec[0]
        vec = [float(v) for v in vec]

        count = self.collection.count()
        if count == 0:
            return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}

        kwargs: dict = {"query_embeddings": [vec], "n_results": min(n_results, count)}
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

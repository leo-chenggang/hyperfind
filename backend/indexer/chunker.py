"""
文本切片器 — 滑动窗口在句子边界切分文本
chunk_size=512, overlap=128, min_chunk=10
"""

import re


class TextChunker:
    """将长文本切分为有重叠的语义块，用于向量索引和搜索"""

    _SENTENCE_BOUNDARY = re.compile(r"[。！？\.!\?\n]+")

    def __init__(self, chunk_size: int = 512, overlap: int = 128, min_chunk: int = 10):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk = min_chunk

    def chunk(self, text: str) -> list[str]:
        """将文本切分为滑动窗口块"""
        text = text.strip()
        if not text:
            return []
        if len(text) < self.min_chunk:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        sentences = [s.strip() for s in self._SENTENCE_BOUNDARY.split(text) if s.strip()]
        if not sentences:
            return self._fixed_chunk(text)

        chunks = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 > self.chunk_size:
                if current and len(current) >= self.min_chunk:
                    chunks.append(current)
                if chunks and self.overlap > 0:
                    prev = chunks[-1]
                    current = (prev[-self.overlap:] + sentence) if len(prev) > self.overlap else sentence
                else:
                    current = sentence
            else:
                current = f"{current} {sentence}" if current else sentence

        if current and len(current) >= self.min_chunk:
            chunks.append(current)
        return chunks if chunks else self._fixed_chunk(text)

    def _fixed_chunk(self, text: str) -> list[str]:
        """固定宽度切分（回退方案）"""
        step = max(self.chunk_size - self.overlap, self.chunk_size)
        return [
            text[i:i + self.chunk_size]
            for i in range(0, len(text), step)
            if len(text[i:i + self.chunk_size]) >= self.min_chunk
        ]

    def chunk_documents(self, raw_chunks: list[dict]) -> list[dict]:
        """对解析器产出的原始块进行二次切片

        输入: [{"content": "...", "char_offset": 0}, ...]
        输出: [{"content": "...", "char_offset": N}, ...]
        """
        results = []
        for rc in raw_chunks:
            text = rc.get("content", "")
            base_offset = rc.get("char_offset", 0)
            sub_chunks = self.chunk(text)
            local_offset = 0
            for sc in sub_chunks:
                idx = text.find(sc, local_offset)
                if idx >= 0:
                    offset = base_offset + idx
                    local_offset = idx + len(sc)
                else:
                    offset = base_offset + local_offset
                    local_offset += len(sc)
                results.append({"content": sc, "char_offset": offset})
        return results

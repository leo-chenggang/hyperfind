"""
文本切片器 — 滑动窗口在句子边界切分文本
chunk_size=512, overlap=128, min_chunk=10
"""

import re


class TextChunker:
    """将长文本切分为重叠的语义块，用于向量索引和搜索"""

    SENTENCE_BOUNDARY = re.compile(r"[。！？\.!\?\n]+")

    def __init__(self, chunk_size: int = 512, overlap: int = 128, min_chunk: int = 10):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk = min_chunk

    def chunk(self, text: str) -> list[str]:
        """
        将文本切分为滑动窗口块。

        返回: 文本块列表，每个块不超过 chunk_size 字符。
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        if len(text) < self.min_chunk:
            return []

        # 如果文本比 chunk_size 短，直接返回
        if len(text) <= self.chunk_size:
            return [text]

        # 在句子边界切分
        sentences = [s.strip() for s in self.SENTENCE_BOUNDARY.split(text) if s.strip()]
        if not sentences:
            return [text[:self.chunk_size]]

        chunks = []
        current = ""
        for sentence in sentences:
            # 如果当前块加上新句子超出限制
            if len(current) + len(sentence) + 1 > self.chunk_size:
                if current and len(current) >= self.min_chunk:
                    chunks.append(current)
                # 用 overlap 开始新块
                if chunks and self.overlap > 0:
                    prev = chunks[-1]
                    if len(prev) > self.overlap:
                        current = prev[-self.overlap:] + sentence
                    else:
                        current = sentence
                else:
                    current = sentence
            else:
                if current:
                    current += " " + sentence
                else:
                    current = sentence

        # 收尾
        if current and len(current) >= self.min_chunk:
            chunks.append(current)

        # 回退：如果句子切分没有产生块，做固定宽度切分
        if not chunks:
            return self._fixed_chunk(text)

        return chunks

    def _fixed_chunk(self, text: str) -> list[str]:
        """固定宽度切分（回退方案）"""
        step = self.chunk_size - self.overlap
        if step <= 0:
            step = self.chunk_size
        chunks = []
        for i in range(0, len(text), step):
            chunk = text[i:i + self.chunk_size]
            if len(chunk) >= self.min_chunk:
                chunks.append(chunk)
        return chunks

    def chunk_documents(self, raw_chunks: list[dict]) -> list[dict]:
        """
        对解析器产出的原始块进行二次切片。

        输入: [{"content": "原始文本", "char_offset": 0}, ...]
        输出: [{"content": "切片文本", "char_offset": 偏移量}, ...]
        """
        results = []
        for rc in raw_chunks:
            text = rc.get("content", "")
            base_offset = rc.get("char_offset", 0)
            sub_chunks = self.chunk(text)
            local_offset = 0
            for sc in sub_chunks:
                # 计算子块在原文本中的偏移
                idx = text.find(sc, local_offset)
                if idx >= 0:
                    local_offset = idx + len(sc)
                    offset = base_offset + idx
                else:
                    offset = base_offset + local_offset
                    local_offset += len(sc)

                results.append({
                    "content": sc,
                    "char_offset": offset,
                })
        return results

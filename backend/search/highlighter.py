"""
搜索结果高亮与摘要提取器
提取匹配词周围的 300 字符上下文窗口，用 <mark> 标签高亮关键词。
"""

import re
import jieba


class SearchHighlighter:
    """关键词高亮 + 上下文摘要提取"""

    CONTEXT_WINDOW = 150  # 匹配词两侧各 150 字符

    def highlight(self, query: str, snippets: list[dict]) -> list[dict]:
        if not query or not snippets:
            return snippets

        keywords = self._extract_keywords(query)
        if not keywords:
            return snippets

        highlighted = []
        for snip in snippets:
            text = snip.get("content", "")
            if not text:
                highlighted.append(snip)
                continue

            positions = self._find_match_positions(text, keywords)
            if not positions:
                highlighted.append(snip)
                continue

            start, end = positions[0]
            center = (start + end) // 2
            ctx_start = max(0, center - self.CONTEXT_WINDOW)
            ctx_end = min(len(text), center + self.CONTEXT_WINDOW)
            ctx_text = text[ctx_start:ctx_end]
            hl_text = self._apply_highlights(ctx_text, keywords)

            prefix = "..." if ctx_start > 0 else ""
            suffix = "..." if ctx_end < len(text) else ""

            highlighted.append({
                "chunk_id": snip["chunk_id"],
                "content": f"{prefix}{hl_text}{suffix}",
                "char_offset": snip.get("char_offset", 0) + ctx_start,
                "score": snip.get("score", 0),
            })

        return highlighted

    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        tokens = list(jieba.cut(query))
        keywords = [t.strip() for t in tokens if len(t.strip()) > 1]
        return keywords if keywords else [query.strip()]

    @staticmethod
    def _find_match_positions(text: str, keywords: list[str]) -> list[tuple[int, int]]:
        positions = []
        for kw in keywords:
            offset = 0
            while (idx := text.find(kw, offset)) != -1:
                positions.append((idx, idx + len(kw)))
                offset = idx + 1
        return sorted(positions)

    @staticmethod
    def _apply_highlights(text: str, keywords: list[str]) -> str:
        sorted_kw = sorted(set(keywords), key=len, reverse=True)
        pattern = "|".join(re.escape(kw) for kw in sorted_kw)
        if not pattern:
            return text
        return re.sub(pattern, lambda m: f"<mark>{m.group()}</mark>", text, flags=re.IGNORECASE)

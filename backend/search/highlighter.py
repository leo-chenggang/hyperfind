"""
搜索结果高亮与摘要提取器
提取匹配词周围的 300 字符上下文窗口，用 <mark> 标签高亮关键词。
"""

import re


class SearchHighlighter:
    """关键词高亮 + 上下文摘要提取"""

    CONTEXT_WINDOW = 150  # 匹配词两侧各 150 字符，共 300 字符

    def highlight(
        self,
        query: str,
        snippets: list[dict],
    ) -> list[dict]:
        """
        对搜索结果片段进行高亮处理。

        Args:
            query: 搜索关键词
            snippets: [{chunk_id, content, char_offset, score}, ...]

        Returns:
            [{chunk_id, content (带 <mark> 标签), char_offset, score}, ...]
        """
        if not query or not snippets:
            return snippets

        # 提取查询词列表（中文按字符，英文按空格分词）
        keywords = self._extract_keywords(query)
        if not keywords:
            return snippets

        # 对每个 snippet 做高亮 + 上下文裁剪
        highlighted = []
        for snip in snippets:
            text = snip.get("content", "")
            if not text:
                highlighted.append(snip)
                continue

            # 找到第一个匹配位置
            match_positions = self._find_match_positions(text, keywords)
            if not match_positions:
                highlighted.append(snip)
                continue

            # 以第一个匹配位置为中心裁剪上下文
            start, end = match_positions[0]
            center = (start + end) // 2

            ctx_start = max(0, center - self.CONTEXT_WINDOW)
            ctx_end = min(len(text), center + self.CONTEXT_WINDOW)

            # 在句子边界微调
            ctx_text = text[ctx_start:ctx_end]

            # 对窗口内文本高亮
            hl_text = self._apply_highlights(ctx_text, keywords)

            # 添加省略号标记
            prefix = "..." if ctx_start > 0 else ""
            suffix = "..." if ctx_end < len(text) else ""

            highlighted.append({
                "chunk_id": snip["chunk_id"],
                "content": prefix + hl_text + suffix,
                "char_offset": snip.get("char_offset", 0) + ctx_start,
                "score": snip.get("score", 0),
            })

        return highlighted

    # ── 内部方法 ──────────────────────────────────────────

    def _extract_keywords(self, query: str) -> list[str]:
        """从查询字符串提取关键词"""
        import jieba
        # 中文分词
        tokens = list(jieba.cut(query))
        # 过滤单字和纯空白
        keywords = [t.strip() for t in tokens if len(t.strip()) > 1]
        if not keywords:
            # 回退：使用原始查询
            keywords = [query.strip()]
        return keywords

    def _find_match_positions(
        self, text: str, keywords: list[str]
    ) -> list[tuple[int, int]]:
        """在文本中找到所有关键词的匹配位置"""
        positions = []
        for kw in keywords:
            offset = 0
            while True:
                idx = text.find(kw, offset)
                if idx == -1:
                    break
                positions.append((idx, idx + len(kw)))
                offset = idx + 1
        return sorted(positions)

    def _apply_highlights(self, text: str, keywords: list[str]) -> str:
        """对文本中的关键词包裹 <mark> 标签"""
        # 按长度降序排列，避免短词先匹配干扰长词
        sorted_kw = sorted(keywords, key=len, reverse=True)

        # 用占位符保护已处理区域
        pattern = "|".join(re.escape(kw) for kw in sorted_kw)
        if not pattern:
            return text

        def replacer(match):
            return f"<mark>{match.group(0)}</mark>"

        return re.sub(pattern, replacer, text, flags=re.IGNORECASE)

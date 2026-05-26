"""
Markdown 解析器 — .md / .markdown
"""

from pathlib import Path


class MarkdownParser:
    """解析 Markdown 文件，提取纯文本"""

    def parse(self, file_path: Path) -> list[dict]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        if not text.strip():
            return []

        # 尝试用 mistune 解析
        try:
            import mistune
            md = mistune.create_markdown(renderer=None)
            plain = mistune.html.unescape(
                mistune.markdown(text)
            )
            # Strip HTML tags after mistune
            import re
            plain = re.sub(r"<[^>]+>", "", plain)
            if plain.strip():
                return [{"content": plain.strip(), "char_offset": 0}]
        except Exception:
            pass

        # 回退：保留原始文本
        return [{"content": text.strip(), "char_offset": 0}]

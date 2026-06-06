"""
Markdown 解析器 — .md / .markdown
"""

import re

from pathlib import Path


_STRIP_HTML = re.compile(r"<[^>]+>")


class MarkdownParser:
    """解析 Markdown 文件，提取纯文本"""

    def parse(self, file_path: Path) -> list[dict]:
        import mistune

        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        if not text.strip():
            return []

        try:
            md = mistune.create_markdown(renderer=None)
            html = md(text)
            plain = _STRIP_HTML.sub("", html)
            if plain.strip():
                return [{"content": plain.strip(), "char_offset": 0}]
        except Exception:
            pass

        return [{"content": text.strip(), "char_offset": 0}]

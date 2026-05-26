"""
HTML 解析器 — .html / .htm
"""

from pathlib import Path


class HTMLParser:
    """解析 HTML 文件，提取纯文本"""

    def parse(self, file_path: Path) -> list[dict]:
        try:
            from bs4 import BeautifulSoup
            html = file_path.read_text(encoding="utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []

        # 移除 script 和 style
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        if not text.strip():
            return []

        return [{"content": text.strip(), "char_offset": 0}]

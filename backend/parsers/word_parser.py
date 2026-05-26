"""
Word 解析器 — .docx
"""

from pathlib import Path


class WordParser:
    """解析 Word 文档，提取段落文本"""

    def parse(self, file_path: Path) -> list[dict]:
        try:
            from docx import Document
            doc = Document(str(file_path))
        except Exception:
            return []

        paragraphs = []
        offset = 0

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

        if not paragraphs:
            # 也检查表格
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    line = " | ".join(cells)
                    if line.strip():
                        paragraphs.append(line)

        if not paragraphs:
            return []

        full_text = "\n".join(paragraphs)
        return [{"content": full_text, "char_offset": 0}]

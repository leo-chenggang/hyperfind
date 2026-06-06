"""
PDF 解析器 — .pdf (pdfplumber)
"""

from pathlib import Path


class PDFParser:
    """解析 PDF 文件，按页提取文本"""

    def parse(self, file_path: Path) -> list[dict]:
        import pdfplumber

        results = []
        offset = 0
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        full = f"[Page {page_num + 1}]\n{text.strip()}"
                        results.append({"content": full, "char_offset": offset})
                        offset += len(full)
        except Exception:
            return []
        return results

"""
PDF 解析器 — .pdf
"""

from pathlib import Path


class PDFParser:
    """解析 PDF 文件，提取文本"""

    def parse(self, file_path: Path) -> list[dict]:
        try:
            import pdfplumber
        except ImportError:
            return []

        results = []
        offset = 0

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        page_header = f"[Page {page_num + 1}]\n"
                        full = page_header + text.strip()
                        results.append({
                            "content": full,
                            "char_offset": offset,
                        })
                        offset += len(full)
        except Exception:
            return []

        return results

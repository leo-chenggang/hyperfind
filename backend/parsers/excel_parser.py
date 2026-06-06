"""
Excel 解析器 — .xlsx / .xls / .csv
"""

from pathlib import Path


class ExcelParser:
    """解析 Excel 文件，提取所有工作表单元格文本"""

    def parse(self, file_path: Path) -> list[dict]:
        ext = file_path.suffix.lower()
        if ext == ".csv":
            return self._parse_csv(file_path)
        return self._parse_xlsx(file_path)

    def _parse_xlsx(self, file_path: Path) -> list[dict]:
        import openpyxl

        try:
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
        except Exception:
            return self._fallback_raw(file_path)

        results = []
        offset = 0
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            lines = [f"[Sheet: {sheet_name}]"]
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                line = "\t".join(cells).strip()
                if line:
                    lines.append(line)
            text = "\n".join(lines)
            if text.strip():
                results.append({"content": text.strip(), "char_offset": offset})
                offset += len(text)
        wb.close()
        return results

    def _parse_csv(self, file_path: Path) -> list[dict]:
        import pandas

        try:
            df = pandas.read_csv(str(file_path), dtype=str)
        except Exception:
            return self._fallback_raw(file_path)

        text = df.to_csv(index=False, header=True)
        return [{"content": text.strip(), "char_offset": 0}] if text.strip() else []

    @staticmethod
    def _fallback_raw(file_path: Path) -> list[dict]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return [{"content": text.strip(), "char_offset": 0}] if text.strip() else []
        except Exception:
            return []

"""
Excel 解析器 — .xlsx / .xls / .csv
"""

from pathlib import Path
from typing import Optional


class ExcelParser:
    """解析 Excel 文件，提取所有单元格文本"""

    def parse(self, file_path: Path) -> list[dict]:
        results = []

        ext = file_path.suffix.lower()
        if ext == ".csv":
            return self._parse_csv(file_path)

        # .xlsx / .xls
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
        except Exception:
            return self._fallback_raw(file_path)

        offset = 0
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheet_text = f"[Sheet: {sheet_name}]\n"
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                line = "\t".join(cells)
                if line.strip():
                    sheet_text += line + "\n"

            if sheet_text.strip():
                results.append({
                    "content": sheet_text.strip(),
                    "char_offset": offset,
                })
                offset += len(sheet_text)

        wb.close()
        return results

    def _parse_csv(self, file_path: Path) -> list[dict]:
        try:
            import pandas
            df = pandas.read_csv(str(file_path), dtype=str)
        except Exception:
            return self._fallback_raw(file_path)

        text = df.to_csv(index=False, header=True)
        if text.strip():
            return [{"content": text.strip(), "char_offset": 0}]
        return []

    def _fallback_raw(self, file_path: Path) -> list[dict]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                return [{"content": text.strip(), "char_offset": 0}]
        except Exception:
            pass
        return []

"""
格式分发器 — 根据文件扩展名路由到对应解析器
"""

from pathlib import Path
from typing import Optional

from backend.parsers.excel_parser import ExcelParser
from backend.parsers.word_parser import WordParser
from backend.parsers.pdf_parser import PDFParser
from backend.parsers.ppt_parser import PPTParser
from backend.parsers.html_parser import HTMLParser
from backend.parsers.markdown_parser import MarkdownParser

# 扩展名 → (解析器, file_type)
PARSER_MAP = {
    ".xlsx": (ExcelParser(), "excel"),
    ".xls":  (ExcelParser(), "excel"),
    ".csv":  (ExcelParser(), "excel"),
    ".docx": (WordParser(), "word"),
    ".pdf":  (PDFParser(), "pdf"),
    ".pptx": (PPTParser(), "powerpoint"),
    ".html": (HTMLParser(), "html"),
    ".htm":  (HTMLParser(), "html"),
    ".md":   (MarkdownParser(), "markdown"),
    ".markdown": (MarkdownParser(), "markdown"),
}


class FormatDispatchError(Exception):
    """不支持的格式"""
    pass


def get_parser(ext: str) -> tuple:
    """返回 (parser_instance, file_type) 或抛出 FormatDispatchError"""
    ext_lower = ext.lower()
    if ext_lower not in PARSER_MAP:
        raise FormatDispatchError(f"不支持的文件格式: {ext}")
    return PARSER_MAP[ext_lower]


def detect_file_type(file_path: Path) -> Optional[str]:
    """根据文件扩展名检测文件类型"""
    ext = file_path.suffix.lower()
    if ext in PARSER_MAP:
        return PARSER_MAP[ext][1]
    return None


def parse_file(file_path: Path) -> list[dict]:
    """
    解析单个文件，返回文本块列表。

    返回: [{"content": "文本", "char_offset": 0}, ...]
    """
    ext = file_path.suffix.lower()
    parser, _ = get_parser(ext)
    return parser.parse(file_path)

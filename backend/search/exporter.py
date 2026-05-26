"""
搜索结果文件导出器
将匹配文件的原始文件复制到用户指定目录。
"""

import shutil
from datetime import datetime
from pathlib import Path

from backend.database import Database


class SearchExporter:
    """匹配文件批量导出"""

    def __init__(self, db: Database):
        self.db = db

    def export(
        self,
        matched_file_ids: list[str],
        target_dir: Path,
    ) -> dict:
        """
        将搜索结果中匹配的所有原文件复制到目标目录。

        Returns:
            {
                "success": bool,
                "copied_count": int,
                "target_dir": str,
                "files": [str, ...],
            }
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        copied = []
        failed = []

        for fid in matched_file_ids:
            file = self.db.get_file(fid)
            if not file:
                failed.append(fid)
                continue

            src = Path(file["original_path"])
            if not src.exists():
                failed.append(file["file_name"])
                continue

            dst = target / src.name
            try:
                shutil.copy2(str(src), str(dst))
                copied.append(file["file_name"])
            except Exception:
                failed.append(file["file_name"])

        return {
            "success": len(failed) == 0,
            "copied_count": len(copied),
            "target_dir": str(target),
            "files": copied,
        }

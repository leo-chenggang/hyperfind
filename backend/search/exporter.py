"""
搜索结果文件导出器
将匹配文件的原始文件复制到用户指定目录。
"""

import shutil
from pathlib import Path

from backend.database import Database


class SearchExporter:
    """匹配文件批量导出"""

    def __init__(self, db: Database):
        self.db = db

    def export(self, matched_file_ids: list[str], target_dir: Path) -> dict:
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

            try:
                dst = target / src.name
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

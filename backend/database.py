"""
HyperFind SQLite 元数据库
管理文件记录和文本块记录。WAL 模式 + 线程安全写入。
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    file_id         TEXT PRIMARY KEY,
    original_path   TEXT NOT NULL,
    library_path    TEXT NOT NULL,
    link_method     TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    file_ext        TEXT NOT NULL,
    file_size       INTEGER NOT NULL,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    uploaded_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_indexed_at TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        TEXT PRIMARY KEY,
    file_id         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    char_offset     INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type);
CREATE INDEX IF NOT EXISTS idx_files_name ON files(file_name);
CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id);
"""


class Database:
    """HyperFind 元数据库"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._init_schema()

    def _connect(self) -> None:
        """连接数据库并启用 WAL 模式"""
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = OFF")

    def _init_schema(self) -> None:
        """初始化数据库表"""
        with self._lock:
            with self._conn:
                self._conn.executescript(SCHEMA_SQL)

    # ── 文件操作 ──────────────────────────────────

    def file_exists(self, md5_hash: str) -> bool:
        """检查文件是否已存在"""
        row = self._conn.execute(
            "SELECT 1 FROM files WHERE file_id = ?", (md5_hash,)
        ).fetchone()
        return row is not None

    def add_file(
        self,
        file_id: str,
        original_path: str,
        library_path: str,
        link_method: str,
        file_name: str,
        file_type: str,
        file_ext: str,
        file_size: int,
        chunk_count: int = 0,
    ) -> None:
        """添加文件记录"""
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """INSERT OR REPLACE INTO files
                       (file_id, original_path, library_path, link_method,
                        file_name, file_type, file_ext, file_size, chunk_count,
                        uploaded_at, last_indexed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                    (file_id, original_path, library_path, link_method,
                     file_name, file_type, file_ext, file_size, chunk_count),
                )

    def get_file(self, file_id: str) -> Optional[dict]:
        """获取单个文件记录"""
        row = self._conn.execute(
            "SELECT * FROM files WHERE file_id = ?", (file_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_files(self) -> list[dict]:
        """获取所有文件记录"""
        rows = self._conn.execute(
            "SELECT * FROM files ORDER BY uploaded_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_files_by_type(self, file_type: str) -> list[dict]:
        """按类型获取文件"""
        rows = self._conn.execute(
            "SELECT * FROM files WHERE file_type = ? ORDER BY uploaded_at DESC",
            (file_type,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_file_count_by_type(self) -> dict:
        """获取各类型文件数量"""
        rows = self._conn.execute(
            "SELECT file_type, COUNT(*) as cnt FROM files GROUP BY file_type"
        ).fetchall()
        return {r["file_type"]: r["cnt"] for r in rows}

    def get_total_files(self) -> int:
        """获取文件总数"""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM files").fetchone()
        return row["cnt"] if row else 0

    def delete_file(self, file_id: str) -> Optional[dict]:
        """删除文件及其关联的文本块记录"""
        file = self.get_file(file_id)
        if not file:
            return None
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM chunks WHERE file_id = ?", (file_id,)
                )
                self._conn.execute(
                    "DELETE FROM files WHERE file_id = ?", (file_id,)
                )
        return file

    def clear_all(self) -> None:
        """清空所有文件和文本块"""
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM chunks")
                self._conn.execute("DELETE FROM files")

    # ── 文本块操作 ──────────────────────────────────

    def add_chunks(self, chunks: list[dict]) -> None:
        """批量添加文本块"""
        with self._lock:
            with self._conn:
                self._conn.executemany(
                    """INSERT OR REPLACE INTO chunks
                       (chunk_id, file_id, chunk_index, content, char_offset, created_at)
                       VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                    [(c["chunk_id"], c["file_id"], c["chunk_index"],
                      c["content"], c["char_offset"]) for c in chunks],
                )

    def get_chunks_by_file(self, file_id: str) -> list[dict]:
        """获取某文件的所有文本块"""
        rows = self._conn.execute(
            "SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index",
            (file_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_file_ids(self) -> list[str]:
        """获取所有文件 ID"""
        rows = self._conn.execute("SELECT file_id FROM files").fetchall()
        return [r["file_id"] for r in rows]

    # ── 状态查询 ──────────────────────────────────

    def get_stats(self) -> dict:
        """获取数据库统计信息"""
        total_files = self.get_total_files()
        by_type = self.get_file_count_by_type()
        total_chunks_row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM chunks"
        ).fetchone()
        total_chunks = total_chunks_row["cnt"] if total_chunks_row else 0

        last_indexed_row = self._conn.execute(
            "SELECT MAX(last_indexed_at) as ts FROM files"
        ).fetchone()
        last_indexed = last_indexed_row["ts"] if last_indexed_row else None

        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_files": total_files,
            "total_chunks": total_chunks,
            "by_type": by_type,
            "last_indexed": last_indexed,
            "db_size_bytes": db_size,
        }

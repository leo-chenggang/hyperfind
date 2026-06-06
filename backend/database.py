"""
HyperFind — SQLite 元数据库
WAL 模式 + 线程安全写入。
管理文件记录、文本块记录，提供统计查询。
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

SCHEMA = """
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
    """HyperFind 元数据库（每应用实例一个连接）"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)          # 防御性包裹
        self._lock = threading.Lock()
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = OFF")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._conn:
                self._conn.executescript(SCHEMA)

    # ── 文件 CRUD ──────────────────────────────────────

    def file_exists(self, file_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM files WHERE file_id = ?", (file_id,)
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
        row = self._conn.execute(
            "SELECT * FROM files WHERE file_id = ?", (file_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_files(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM files ORDER BY uploaded_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_files_by_type(self, file_type: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM files WHERE file_type = ? ORDER BY uploaded_at DESC",
            (file_type,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_file_count_by_type(self) -> dict:
        rows = self._conn.execute(
            "SELECT file_type, COUNT(*) AS cnt FROM files GROUP BY file_type"
        ).fetchall()
        return {r["file_type"]: r["cnt"] for r in rows}

    def get_total_files(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM files").fetchone()
        return row["cnt"] if row else 0

    def get_all_file_ids(self) -> list[str]:
        rows = self._conn.execute("SELECT file_id FROM files").fetchall()
        return [r["file_id"] for r in rows]

    def delete_file(self, file_id: str) -> Optional[dict]:
        file = self.get_file(file_id)
        if not file:
            return None
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
                self._conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        return file

    def clear_all(self) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM chunks")
                self._conn.execute("DELETE FROM files")

    # ── 文本块 ──────────────────────────────────────────

    def add_chunks(self, chunks: list[dict]) -> None:
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
        rows = self._conn.execute(
            "SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index",
            (file_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_chunk(self, chunk_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── 统计 ────────────────────────────────────────────

    def get_stats(self) -> dict:
        total_files = self.get_total_files()
        by_type = self.get_file_count_by_type()

        row_chunks = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM chunks"
        ).fetchone()
        total_chunks = row_chunks["cnt"] if row_chunks else 0

        row_last = self._conn.execute(
            "SELECT MAX(last_indexed_at) AS ts FROM files"
        ).fetchone()
        last_indexed = row_last["ts"] if row_last else None

        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_files": total_files,
            "total_chunks": total_chunks,
            "by_type": by_type,
            "last_indexed": last_indexed,
            "db_size_bytes": db_size,
        }

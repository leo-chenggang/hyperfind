"""
HyperFind — 本地文件管理与智能搜索桌面应用
入口文件: pywebview 窗口 + 后端 API 桥接
"""

import atexit
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import webview

# ── macOS PyInstaller 防重复启动 ──
if sys.platform == "darwin":
    sys.argv = [a for a in sys.argv if not a.startswith("-psn_")]
    if "-NSDocumentRevisionsDebugMode" in sys.argv:
        idx = sys.argv.index("-NSDocumentRevisionsDebugMode")
        sys.argv = sys.argv[:idx] + sys.argv[idx + 2:]

import multiprocessing
multiprocessing.freeze_support()

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import AppConfig
from backend.database import Database
from backend.upload.engine import ConcurrentUploadEngine
from backend.search.engine import HybridSearchEngine
from backend.search.highlighter import SearchHighlighter
from backend.cleaner import cleanup_on_exit


class HyperFindAPI:
    """pywebview JS API 桥接层 — 所有 window.pywebview.api.xxx() 方法"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.db: Optional[Database] = None
        self._window: Optional[webview.Window] = None
        self._upload_engine: Optional[ConcurrentUploadEngine] = None
        self._search_engine: Optional[HybridSearchEngine] = None
        self._highlighter = SearchHighlighter()
        self._tasks: dict = {}
        self._last_notify: dict = {}

        # ensure_dirs 需要 Path 对象 — 在转换前调用
        config.ensure_dirs()

        # 保存原始 Path 引用（内部使用）
        self._lib_dir = config.library_dir

        # pywebview 6.x 序列化 js_api 的全部属性，Path 的私有属性会导致非致命错误日志。
        # 将全部 Path 属性转为 str。需要 Path 的内部方法使用 _lib_dir。
        config.data_home = str(config.data_home)
        config.library_dir = str(config.library_dir)
        config.db_path = str(config.db_path)
        config.chroma_dir = str(config.chroma_dir)
        config.cache_dir = str(config.cache_dir)
        config.model_dir = str(config.model_dir)
        config.bm25_path = str(config.bm25_path)

    def initialize(self) -> None:
        """后台异步初始化（在 webview on_loaded 线程中调用）"""
        try:
            self.db = Database(Path(self.config.db_path))

            self._upload_engine = ConcurrentUploadEngine(
                self.config, self.db, notify_callback=self._notify_ui
            )
            self._search_engine = HybridSearchEngine(self.db, self._upload_engine)
            self._notify_ui("app:ready", {
                "version": "1.0.0",
                "total_files": self.db.get_total_files(),
            })
        except Exception as e:
            import traceback
            print("[INIT ERROR]", traceback.format_exc())
            self._notify_ui("app:error", {"message": str(e)})

    def _notify_ui(self, event: str, data: dict) -> None:
        """推送事件到前端（进度事件防抖 + 状态变更放行）"""
        if not self._window:
            return

        if event == "file:progress":
            key = f"{event}:{data.get('index', 0)}"
            new_status = data.get("status", "")
            last = self._last_notify.get(key, {})
            if last.get("status") == new_status:
                if time.time() - last.get("time", 0) < 0.2:
                    return
            self._last_notify[key] = {"time": time.time(), "status": new_status}

        try:
            payload = json.dumps(
                {"event": event, "data": data},
                ensure_ascii=False,
                default=str,
            )
            self._window.evaluate_js(f"window.onBackendEvent({payload})")
        except Exception:
            pass

    # ── 上传 ──────────────────────────────────────────

    def select_files(self):
        try:
            result = webview.windows[0].create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=(
                    "All Supported (*.xlsx;*.xls;*.csv;*.docx;*.pdf;*.pptx;*.html;*.htm;*.md)",
                    "Excel (*.xlsx;*.xls;*.csv)",
                    "Word (*.docx)",
                    "PDF (*.pdf)",
                    "PowerPoint (*.pptx)",
                    "HTML (*.html;*.htm)",
                    "Markdown (*.md)",
                ),
            )
            if result is None:
                return []
            cleaned = []
            for p in (result if isinstance(result, (list, tuple)) else [result]):
                p_str = str(p)
                if p_str.startswith("file://"):
                    from urllib.parse import unquote
                    p_str = unquote(p_str[7:])
                cleaned.append(p_str)
            return cleaned
        except Exception:
            return []

    def upload_files(self, file_paths):
        """上传文件到仓库（顺序阻塞处理，所有进度通过事件推送）"""
        if not self._upload_engine:
            return {"results": [{"index": i, "file_name": Path(p).name,
                                 "success": False, "error": "引擎未初始化"}
                                for i, p in enumerate(file_paths)]}

        paths = [Path(p) for p in file_paths]
        for i, p in enumerate(paths):
            self._tasks[f"upload_{i}_{p.name}"] = {
                "index": i, "file_name": p.name,
                "status": "waiting", "progress": 0.0,
            }

        def _run():
            try:
                results = []
                for i, p in enumerate(paths):
                    try:
                        r = self._upload_engine._process_one(p, i, len(paths))
                        results.append(r)
                        tid = f"upload_{i}_{p.name}"
                        self._tasks.get(tid, {})["status"] = "done" if r["success"] else "error"
                        self._tasks.get(tid, {})["progress"] = 1.0 if r["success"] else 0.0
                    except Exception as e:
                        results.append({
                            "index": i, "file_name": p.name,
                            "success": False, "error": str(e),
                        })
                self._notify_ui("file:uploaded", {"count": len(paths)})
            except Exception as e:
                self._notify_ui("app:error", {"message": str(e)})

        threading.Thread(target=_run, daemon=True).start()
        return {"task_ids": list(self._tasks.keys()), "results": []}

    def get_upload_tasks(self):
        """查询上传任务状态"""
        return [
            {"task_id": tid, **state}
            for tid, state in self._tasks.items()
            if state.get("status") not in ("done", "error")
        ]

    # ── 文件仓库 ──────────────────────────────────────

    def get_file_repository(self):
        if not self.db:
            return {"total": 0, "by_type": {}}
        stats = self.db.get_stats()
        return {"total": stats["total_files"], "by_type": stats["by_type"]}

    def get_files_by_type(self, file_type: str):
        return self.db.get_files_by_type(file_type) if self.db else []

    def delete_file(self, file_id: str):
        if not self.db:
            return {"success": False, "error": "数据库未初始化"}

        file = self.db.delete_file(file_id)
        if not file:
            return {"success": False, "error": "文件不存在"}

        lib_path = Path(file["library_path"])
        if lib_path.exists():
            try:
                lib_path.unlink()
            except OSError:
                pass

        if self._upload_engine:
            try:
                self._upload_engine.vector_store.delete_by_file_id(file_id)
            except Exception:
                pass
            with self._upload_engine._bm25_lock:
                self._upload_engine._bm25_dirty = True
                # 从待处理数据中移除该文件的 chunks
                keep_texts = []
                keep_ids = []
                for tid, text in zip(self._upload_engine._bm25_pending_ids,
                                     self._upload_engine._bm25_pending_texts):
                    if not tid.startswith(file_id):
                        keep_ids.append(tid)
                        keep_texts.append(text)
                self._upload_engine._bm25_pending_texts = keep_texts
                self._upload_engine._bm25_pending_ids = keep_ids

        self._notify_ui("file:deleted", {
            "file_id": file_id, "file_type": file["file_type"],
        })
        return {"success": True, "file_name": file["file_name"]}

    def clear_all_files(self):
        if not self.db:
            return {"success": False, "error": "数据库未初始化"}

        files = self.db.get_all_files()
        import shutil
        for ft in ("Excel", "Word", "PDF", "PowerPoint", "HTML", "Markdown"):
            lib_dir = self._lib_dir / ft
            if lib_dir.exists():
                shutil.rmtree(lib_dir)
                lib_dir.mkdir(parents=True, exist_ok=True)

        self.db.clear_all()
        if self._upload_engine:
            try:
                self._upload_engine.vector_store.clear_all()
            except Exception:
                pass
            with self._upload_engine._bm25_lock:
                self._upload_engine._bm25_pending_texts.clear()
                self._upload_engine._bm25_pending_ids.clear()
                self._upload_engine._bm25_dirty = True
                self._upload_engine.bm25_store.index([], [])

        self._notify_ui("files:cleared", {})
        return {"success": True, "deleted_count": len(files)}

    # ── 搜索 ──────────────────────────────────────────

    def search(self, query: str, file_type_filter: str = "all",
               search_mode: str = "hybrid", threshold: int = 2):
        if not self._search_engine:
            return {"query": query, "total_files": 0, "total_hits": 0,
                    "search_time_ms": 0, "results": []}
        result = self._search_engine.search(query, file_type_filter, search_mode)
        if result["results"]:
            for r in result["results"]:
                r["snippets"] = self._highlighter.highlight(query, r["snippets"])
        return result

    def open_file(self, file_path: str):
        import subprocess
        fpath = Path(file_path)
        if not fpath.exists():
            return {"success": False, "error": "文件不存在"}
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(fpath)], check=True)
            elif sys.platform == "win32":
                os.startfile(str(fpath))
            else:
                subprocess.run(["xdg-open", str(fpath)], check=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def export_matched_files(self, file_ids):
        if not file_ids:
            return {"success": False, "error": "没有文件 ID"}
        try:
            target = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
            if not target:
                return {"success": False, "error": "未选择目标文件夹"}
            target_dir = Path(target[0] if isinstance(target, (list, tuple)) else str(target))
        except Exception:
            return {"success": False, "error": "文件夹选择失败"}

        import shutil
        copied = []
        for fid in file_ids:
            f = self.db.get_file(fid) if self.db else None
            if f:
                src = Path(f["original_path"])
                if src.exists():
                    dst = target_dir / src.name
                    shutil.copy2(str(src), str(dst))
                    copied.append(src.name)

        return {"success": True, "copied_count": len(copied),
                "target_dir": str(target_dir), "files": copied}

    # ── 系统状态 ──────────────────────────────────────

    def get_app_status(self):
        if not self.db:
            return {"total_files": 0, "total_chunks": 0,
                    "link_counts": {}, "last_indexed": None}
        stats = self.db.get_stats()

        link_counts = {"hardlink": 0, "symlink": 0, "clonefile": 0, "copy": 0}
        for f in self.db.get_all_files():
            method = f.get("link_method", "")
            if method in link_counts:
                link_counts[method] += 1
            elif method == "chunked_copy":
                link_counts["copy"] += 1

        return {
            "total_files": stats["total_files"],
            "total_chunks": stats["total_chunks"],
            "link_counts": link_counts,
            "last_indexed": stats["last_indexed"],
        }


# ═══════════════════════════════════════════════════════
# Main Entry — 单实例锁 + _window_created 守卫
# ═══════════════════════════════════════════════════════

_window_created = False


def main():
    global _window_created

    # PID 锁 — 防止重复启动
    lock_path = Path(tempfile.gettempdir()) / "hyperfind.pid"
    try:
        if lock_path.exists():
            old_pid = int(lock_path.read_text().strip())
            try:
                os.kill(old_pid, 0)
                return  # 已有实例运行
            except (OSError, ProcessLookupError):
                pass
        lock_path.write_text(str(os.getpid()))
        atexit.register(lambda: lock_path.unlink(missing_ok=True))
    except Exception:
        pass

    if _window_created:
        return
    _window_created = True

    config = AppConfig()
    api = HyperFindAPI(config)

    window = webview.create_window(
        title="HyperFind",
        url=str(PROJECT_ROOT / "frontend" / "index.html"),
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 600),
        text_select=True,
        confirm_close=False,
    )
    api._window = window

    def on_loaded():
        threading.Thread(target=api.initialize, daemon=True).start()

    window.events.loaded += on_loaded
    webview.start(debug=False, private_mode=False)

    # 退出时清理缓存
    cleanup_on_exit(config.cache_dir)


if __name__ == "__main__":
    main()

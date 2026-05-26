"""
HyperFind — 本地文件管理与智能搜索桌面应用
入口文件: pywebview 窗口 + 后端 API 桥接
"""

import json
import sys
import threading
from pathlib import Path
from typing import Optional

import webview

# ── macOS PyInstaller 防重复启动 ──────────────────────────
if sys.platform == "darwin":
    sys.argv = [arg for arg in sys.argv if not arg.startswith("-psn_")]
    if "-NSDocumentRevisionsDebugMode" in sys.argv:
        idx = sys.argv.index("-NSDocumentRevisionsDebugMode")
        sys.argv = sys.argv[:idx] + sys.argv[idx + 2:]

import multiprocessing  # noqa: E402
multiprocessing.freeze_support()

# ── 项目根目录 ────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent

# ── 后端模块 ───────────────────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT))
from backend.config import AppConfig        # noqa: E402
from backend.database import Database       # noqa: E402
from backend.upload.engine import ConcurrentUploadEngine  # noqa: E402
from backend.search.engine import HybridSearchEngine     # noqa: E402
from backend.search.highlighter import SearchHighlighter  # noqa: E402


# ═══════════════════════════════════════════════════════════
# HyperFind API — 暴露给前端的全部方法
# ═══════════════════════════════════════════════════════════

class HyperFindAPI:
    """pywebview JS API 桥接层"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.db: Optional[Database] = None
        self._window: Optional[webview.Window] = None
        self._upload_engine: Optional[ConcurrentUploadEngine] = None
        self._search_engine: Optional[HybridSearchEngine] = None
        self._highlighter = SearchHighlighter()
        self._tasks: dict = {}
        self._last_notify: dict = {}  # debounce progress events

        # 在转换路径之前确保目录存在（Path 方法需要 Path 对象）
        config.ensure_dirs()

        # ── 修复 pywebview Path 序列化警告 ──
        # pywebview 6.x 序列化 js_api 的所有属性，Path 的私有属性
        # (_cached_cparts, _hash, _pparts 等) 会导致非致命错误日志。
        # 将 Path 属性转为 str，内部保留原始 Path 引用。
        self._lib_dir = config.library_dir
        self._chroma_dir = config.chroma_dir
        self._cache_dir = config.cache_dir
        config.library_dir = str(config.library_dir)
        config.db_path = str(config.db_path)
        config.chroma_dir = str(config.chroma_dir)
        config.cache_dir = str(config.cache_dir)
        config.model_dir = str(config.model_dir)
        config.bm25_path = str(config.bm25_path)

    def initialize(self) -> None:
        """后台异步初始化（在 on_loaded 线程中调用）"""
        try:
            # ensure_dirs() 已在 __init__ 中调用
            self._notify_ui("app:init", {"status": "连接数据库..."})
            self.db = Database(self.config.db_path)

            self._notify_ui("app:init", {"status": "启动上传引擎..."})
            self._upload_engine = ConcurrentUploadEngine(
                self.config, self.db, notify_callback=self._notify_ui
            )

            self._notify_ui("app:init", {"status": "启动搜索引擎..."})
            self._search_engine = HybridSearchEngine(
                self.db,
                self._upload_engine.embedder,
                self._upload_engine.vector_store,
                self._upload_engine.bm25_store,
            )

            self._notify_ui("app:ready", {
                "version": "1.0.0",
                "total_files": self.db.get_total_files(),
            })
        except Exception as e:
            import traceback
            print("[INIT ERROR]", traceback.format_exc())
            self._notify_ui("app:error", {"message": str(e)})

    # ── 内部方法 ──────────────────────────────────────────

    def _notify_ui(self, event: str, data: dict) -> None:
        """推送事件到前端（pywebview 6.x evaluate_js 线程安全）"""
        if not self._window:
            return
        # 进度事件防抖: 同文件同状态 200ms 内不重复推送（但状态变更必须放行）
        if event == "file:progress":
            key = f"{event}:{data.get('index', 0)}"
            now = __import__('time').time()
            new_status = data.get("status", "")
            last = self._last_notify.get(key, {})
            # 状态变了 → 必须推送（如 linking→parsing→done）
            if last.get("status") == new_status:
                if now - last.get("time", 0) < 0.2:
                    return
            self._last_notify[key] = {"time": now, "status": new_status}
        try:
            payload = json.dumps(
                {"event": event, "data": data},
                ensure_ascii=False,
                default=str,
            )
            self._window.evaluate_js(f"window.onBackendEvent({payload})")
        except Exception:
            pass  # 窗口可能已关闭

    # ── 上传 ──────────────────────────────────────────────

    def select_files(self):
        """打开原生文件选择器"""
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
            # macOS may return file:// URLs
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
        """上传文件到仓库（非阻塞 — 后台线程处理）"""
        if not self._upload_engine:
            return {"results": [], "error": "上传引擎未初始化"}

        # 初始化任务追踪
        task_ids = []
        for i, fp in enumerate(file_paths):
            tid = f"upload_{i}_{Path(fp).name}"
            self._tasks[tid] = {
                "index": i, "file_name": Path(fp).name,
                "status": "waiting", "progress": 0.0,
            }
            task_ids.append(tid)

        def _run():
            try:
                results = []
                for i, fp in enumerate(file_paths):
                    try:
                        r = self._upload_engine._process_one(
                            Path(fp), i, len(file_paths)
                        )
                        results.append(r)
                        tid = task_ids[i]
                        self._tasks[tid]["status"] = "done" if r["success"] else "error"
                        self._tasks[tid]["progress"] = 1.0 if r["success"] else 0.0
                        self._tasks[tid]["error"] = r.get("error")
                    except Exception as ex:
                        results.append({
                            "index": i, "file_name": Path(fp).name,
                            "success": False, "error": str(ex),
                        })
                        self._tasks[task_ids[i]]["status"] = "error"
                        self._tasks[task_ids[i]]["error"] = str(ex)
                self._notify_ui("file:uploaded", {"count": len(file_paths)})
            except Exception as e:
                for tid in task_ids:
                    self._tasks[tid]["status"] = "error"
                    self._tasks[tid]["error"] = str(e)
                self._notify_ui("app:error", {"message": str(e)})

        threading.Thread(target=_run, daemon=True).start()
        return {"task_ids": task_ids, "results": []}

    def get_upload_tasks(self):
        """查询上传任务状态"""
        return [
            {"task_id": tid, **state}
            for tid, state in self._tasks.items()
            if state["status"] not in ("done", "error")
        ]

    # ── 文件仓库 ──────────────────────────────────────────

    def get_file_repository(self):
        """获取文件仓库概览"""
        if not self.db:
            return {"total": 0, "by_type": {}}
        stats = self.db.get_stats()
        return {
            "total": stats["total_files"],
            "by_type": stats["by_type"],
        }

    def get_files_by_type(self, file_type: str):
        """获取指定类型的文件列表"""
        if not self.db:
            return []
        return self.db.get_files_by_type(file_type)

    def delete_file(self, file_id: str):
        """删除文件及其索引"""
        if not self.db:
            return {"success": False, "error": "数据库未初始化"}
        file = self.db.delete_file(file_id)
        if file:
            # 删除硬链接文件
            lib_path = Path(file["library_path"])
            if lib_path.exists():
                try:
                    lib_path.unlink()
                except OSError:
                    pass
            # 清理 ChromaDB 向量
            if self._upload_engine:
                try:
                    self._upload_engine.vector_store.delete_by_file_id(file_id)
                except Exception:
                    pass
                try:
                    self._upload_engine.bm25_store.remove_by_prefix(file_id)
                except Exception:
                    pass
            self._notify_ui("file:deleted", {
                "file_id": file_id,
                "file_type": file["file_type"],
            })
            return {"success": True, "file_name": file["file_name"]}
        return {"success": False, "error": "文件不存在"}

    def clear_all_files(self):
        """清空全部索引"""
        if not self.db:
            return {"success": False, "error": "数据库未初始化"}
        files = self.db.get_all_files()
        # 删除所有硬链接
        import shutil
        for ft in ("Excel", "Word", "PDF", "PowerPoint", "HTML", "Markdown"):
            lib_dir = self._lib_dir / ft
            if lib_dir.exists():
                shutil.rmtree(lib_dir)
                lib_dir.mkdir(parents=True, exist_ok=True)
        # 清空数据库
        self.db.clear_all()
        # 清空 ChromaDB + BM25
        if self._upload_engine:
            try:
                self._upload_engine.vector_store.clear_all()
            except Exception:
                pass
            try:
                self._upload_engine.bm25_store.index([], [])
            except Exception:
                pass
        self._notify_ui("files:cleared", {})
        return {"success": True, "deleted_count": len(files)}

    # ── 搜索 ──────────────────────────────────────────────

    def search(self, query: str, file_type_filter: str = "all",
               search_mode: str = "hybrid", threshold: int = 2):
        """混合搜索（BM25 + 向量 + RRF 融合）"""
        if not self._search_engine:
            return {
                "query": query,
                "total_files": 0,
                "total_hits": 0,
                "search_time_ms": 0,
                "results": [],
            }
        result = self._search_engine.search(query, file_type_filter, search_mode)
        # 高亮处理
        if result["results"]:
            for r in result["results"]:
                r["snippets"] = self._highlighter.highlight(query, r["snippets"])
        return result

    def open_file(self, file_path: str):
        """用系统默认程序打开文件"""
        import subprocess
        fpath = Path(file_path)
        if not fpath.exists():
            return {"success": False, "error": "文件不存在"}
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(fpath)], check=True)
            elif sys.platform == "win32":
                import os
                os.startfile(str(fpath))
            else:
                subprocess.run(["xdg-open", str(fpath)], check=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def export_matched_files(self, file_ids):
        """导出匹配文件到目标文件夹"""
        if not file_ids:
            return {"success": False, "error": "没有文件 ID"}
        # 打开文件夹选择器
        try:
            target = webview.windows[0].create_file_dialog(
                webview.FileDialog.FOLDER,
            )
            if not target:
                return {"success": False, "error": "未选择目标文件夹"}
            target_dir = Path(target[0] if isinstance(target, (list, tuple)) else str(target))
        except Exception:
            return {"success": False, "error": "文件夹选择失败"}

        # 复制文件
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

        return {
            "success": True,
            "copied_count": len(copied),
            "target_dir": str(target_dir),
            "files": copied,
        }

    # ── 系统状态 ──────────────────────────────────────────

    def get_app_status(self):
        """获取应用状态"""
        if not self.db:
            return {
                "total_files": 0, "total_chunks": 0,
                "link_counts": {}, "last_indexed": None,
            }
        stats = self.db.get_stats()

        # 统计链接方式
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


# ═══════════════════════════════════════════════════════════
# Main Entry
# ═══════════════════════════════════════════════════════════

import atexit
import tempfile

def main():
    # PID 锁防重复启动（崩溃后自动失效）
    lock_path = Path(tempfile.gettempdir()) / "hyperfind.pid"
    try:
        if lock_path.exists():
            old_pid = int(lock_path.read_text().strip())
            try:
                os.kill(old_pid, 0)  # 检查进程是否存活
                return  # 已有实例运行
            except (OSError, ProcessLookupError):
                pass  # 旧进程已死，继续
        lock_path.write_text(str(os.getpid()))
        atexit.register(lambda: lock_path.unlink(missing_ok=True))
    except Exception:
        pass

    config = AppConfig()
    config.ensure_dirs()
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
        """窗口加载完成后异步初始化后端"""
        threading.Thread(target=api.initialize, daemon=True).start()

    window.events.loaded += on_loaded

    webview.start(debug=True, private_mode=False)

    # ── 退出时清理 ──
    config.clear_cache()


if __name__ == "__main__":
    main()

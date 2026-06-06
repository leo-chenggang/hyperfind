"""
HyperFind — 本地文件管理与智能搜索桌面应用
入口文件: pywebview 窗口 + 后端 API 桥接
"""

import json
import os
import sys
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
# Main Entry — 单实例锁 + 立即显示窗口
# ═══════════════════════════════════════════════════════

SPLASH_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:100%;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;background:#fff;color:#1A1A2E;-webkit-font-smoothing:antialiased}
.loading-overlay{position:fixed;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:16px}
.spinner{width:36px;height:36px;border:3px solid #DEE2E6;border-top-color:#4263EB;border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.title{font-size:18px;font-weight:700;letter-spacing:-0.02em}
.status{font-size:13px;color:#6C757D}
.bar-track{width:200px;height:4px;background:#E9ECEF;border-radius:2px;overflow:hidden}
.bar-fill{height:100%;background:#4263EB;border-radius:2px;width:0%;transition:width 0.3s}
</style></head>
<body>
<div class="loading-overlay">
    <div class="spinner"></div>
    <div class="title">HyperFind</div>
    <div class="status" id="status">正在启动...</div>
    <div class="bar-track"><div class="bar-fill" id="bar"></div></div>
</div>
<script>
window.onBackendEvent=function(p){try{var d=typeof p==='string'?JSON.parse(p):p;var e=d.event,dd=d.data;
if(e==='splash:progress'){var s=document.getElementById('status');if(s)s.textContent=dd.status||'';var b=document.getElementById('bar');if(b)b.style.width=(dd.progress||0)*100+'%'}
}catch(_){}}
</script>
</body>
</html>"""

def main():
    config = AppConfig()
    api = HyperFindAPI(config)

    # 使用 inline HTML 立即显示窗口（零文件 I/O）
    window = webview.create_window(
        title="HyperFind",
        html=SPLASH_HTML,
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 600),
        text_select=True,
        confirm_close=False,
    )
    api._window = window

    frontend_index = PROJECT_ROOT / "frontend" / "index.html"
    if not frontend_index.exists():
        if getattr(sys, "frozen", False):
            alt = PROJECT_ROOT.parent / "Resources" / "frontend" / "index.html"
            if alt.exists():
                frontend_index = alt
    if not frontend_index.exists():
        alt2 = Path(sys.executable).parent / "frontend" / "index.html" if getattr(sys, "frozen", False) else None
        if alt2 and alt2.exists():
            frontend_index = alt2
    frontend_url = "file://" + str(frontend_index)
    _splash_done = False  # 防止 loaded 事件死循环

    def on_loaded():
        """Splash 加载完成 → 后台初始化引擎 → 切换到完整前端（仅执行一次）"""
        nonlocal _splash_done
        if _splash_done:
            return  # 完整前端加载后不再触发
        _splash_done = True

        def _init():
            time.sleep(0.2)  # 等 JS event handler 就绪

            api._notify_ui("splash:progress", {"status": "连接数据库...", "progress": 0.15})
            try:
                api.db = Database(Path(api.config.db_path))
            except Exception as e:
                api._notify_ui("splash:progress", {"status": "数据库错误: " + str(e), "progress": 0})
                return

            api._notify_ui("splash:progress", {"status": "启动搜索引擎...", "progress": 0.40})
            try:
                api._upload_engine = ConcurrentUploadEngine(
                    api.config, api.db, notify_callback=api._notify_ui
                )
            except Exception as e:
                api._notify_ui("splash:progress", {"status": "引擎错误: " + str(e), "progress": 0})
                return

            api._notify_ui("splash:progress", {"status": "准备完成...", "progress": 0.80})
            try:
                api._search_engine = HybridSearchEngine(api.db, api._upload_engine)
            except Exception as e:
                api._notify_ui("splash:progress", {"status": "搜索错误: " + str(e), "progress": 0})
                return

            api._notify_ui("splash:progress", {"status": "加载界面...", "progress": 1.0})
            time.sleep(0.3)
            api._window.load_url(frontend_url)

        threading.Thread(target=_init, daemon=True).start()

    window.events.loaded += on_loaded
    webview.start(debug=False, private_mode=False)

    cleanup_on_exit(config.cache_dir)


if __name__ == "__main__":
    main()

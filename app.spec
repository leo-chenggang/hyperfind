# -*- mode: python ; coding: utf-8 -*-
"""
HyperFind — PyInstaller 打包配置 (macOS + Windows)
"""

import sys
from pathlib import Path

# ── 项目根目录 ──
PROJECT_ROOT = Path(SPECPATH).resolve()
MODEL_DIR = PROJECT_ROOT / "models" / "multilingual-minilm"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# ── 收集 ChromaDB 子模块 ──
try:
    from PyInstaller.utils.hooks import collect_submodules
    chromadb_hidden = collect_submodules('chromadb')
except Exception:
    chromadb_hidden = []

# ── 排除用户级冗余 ──
EXCLUDES = [
    "torch", "torchvision", "torchaudio",
    "scipy", "scikit-learn", "sklearn",
    "sentence_transformers", "sentence-transformers",
    "markitdown", "matplotlib", "PIL", "Pillow",
]

# ── 数据文件 ──
ADDED_FILES = [
    ("frontend", "frontend"),
    (str(MODEL_DIR / "model.onnx"), "models/multilingual-minilm"),
    (str(MODEL_DIR / "tokenizer.json"), "models/multilingual-minilm"),
    (str(MODEL_DIR / "tokenizer_config.json"), "models/multilingual-minilm"),
    (str(MODEL_DIR / "special_tokens_map.json"), "models/multilingual-minilm"),
    (str(MODEL_DIR / "tokenizer"), "models/multilingual-minilm/tokenizer"),
]

# pywebview JS assets (required for bundled app)
import webview as _wv
_webview_js = Path(_wv.__path__[0]) / "js"
ADDED_FILES.append((str(_webview_js), "webview/js"))

# chromadb migration/proto data (SQL files PyInstaller misses)
import chromadb as _cdb
_chromadb_root = Path(_cdb.__path__[0])
ADDED_FILES.append((str(_chromadb_root / "migrations"), "chromadb/migrations"))
ADDED_FILES.append((str(_chromadb_root / "proto"), "chromadb/proto"))

# ── 平台特定 webview 后端 ──
if IS_MAC:
    WEBVIEW_BACKENDS = ["webview.platforms.cocoa"]
elif IS_WIN:
    WEBVIEW_BACKENDS = [
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
    ]
else:
    WEBVIEW_BACKENDS = ["webview.platforms.gtk"]

# ── 平台特定排除 ──
if IS_WIN:
    EXCLUDES += ["webview.platforms.cocoa", "webview.platforms.gtk"]

HIDDEN_IMPORTS = [
    # backend
    "backend", "backend.config", "backend.database", "backend.cleaner",
    "backend.upload", "backend.upload.engine", "backend.upload.link_manager",
    "backend.parsers", "backend.parsers.dispatcher",
    "backend.parsers.excel_parser", "backend.parsers.word_parser",
    "backend.parsers.pdf_parser", "backend.parsers.ppt_parser",
    "backend.parsers.html_parser", "backend.parsers.markdown_parser",
    "backend.indexer", "backend.indexer.chunker",
    "backend.indexer.embedder", "backend.indexer.vector_store",
    "backend.indexer.bm25_store",
    "backend.search", "backend.search.engine",
    "backend.search.highlighter", "backend.search.exporter",
    # webview
    "webview", *WEBVIEW_BACKENDS,
    # chromadb
    "chromadb", "chromadb.config",
    "chromadb.segment.impl.metadata.sqlite",
    "chromadb.segment.impl.vector.local_hnsw",
    "chromadb.segment.impl.vector.local_persistent_hnsw",
    *chromadb_hidden,
    # onnx + transformers
    "onnxruntime", "onnxruntime.capi",
    "transformers", "transformers.models.bert.tokenization_bert",
    "tokenizers",
    # search
    "jieba", "bm25s",
    # parsers
    "openpyxl", "docx", "pdfplumber", "pptx", "bs4",
    # data
    "sqlite3", "_sqlite3",
    "pandas", "numpy",
    # misc
    "pkg_resources", "jinja2", "markupsafe",
    "safetensors", "regex",
]

A = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=ADDED_FILES,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(A.pure)

exe = EXE(
    pyz,
    A.scripts,
    A.binaries,
    A.datas,
    [],
    name="HyperFind",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.png" if Path("assets/icon.png").exists() else None,
)

if IS_MAC:
    app = BUNDLE(
        exe,
        name="HyperFind.app",
        icon="assets/icon.png" if Path("assets/icon.png").exists() else None,
        bundle_identifier="com.hyperfind.app",
        info_plist={
            "NSPrincipalClass": "NSApplication",
            "NSHighResolutionCapable": True,
            "LSUIElement": False,
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "CFBundleName": "HyperFind",
            "CFBundleDisplayName": "HyperFind",
            "CFBundleDocumentTypes": [],
        },
    )

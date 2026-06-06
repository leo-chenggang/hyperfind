# -*- mode: python ; coding: utf-8 -*-
"""
HyperFind — PyInstaller 打包配置
macOS: COLLECT 目录模式（零解压延迟）
Windows: EXE 单文件模式
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve()
MODEL_DIR = PROJECT_ROOT / "models" / "multilingual-minilm"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

try:
    from PyInstaller.utils.hooks import collect_submodules
    chromadb_hidden = collect_submodules('chromadb')
except Exception:
    chromadb_hidden = []

EXCLUDES = [
    "torch", "torchvision", "torchaudio",
    "scipy", "scikit-learn", "sklearn",
    "sentence_transformers", "sentence-transformers",
    "markitdown", "matplotlib", "PIL", "Pillow",
]

ADDED_FILES = [
    ("frontend", "frontend"),
    (str(MODEL_DIR / "model.onnx"), "models/multilingual-minilm"),
    (str(MODEL_DIR / "tokenizer.json"), "models/multilingual-minilm"),
    (str(MODEL_DIR / "tokenizer_config.json"), "models/multilingual-minilm"),
    (str(MODEL_DIR / "special_tokens_map.json"), "models/multilingual-minilm"),
]

_tok_dir = MODEL_DIR / "tokenizer"
if _tok_dir.exists():
    ADDED_FILES.append((str(_tok_dir), "models/multilingual-minilm/tokenizer"))

import webview as _wv
_webview_js = Path(_wv.__path__[0]) / "js"
ADDED_FILES.append((str(_webview_js), "webview/js"))

import chromadb as _cdb
_cdb_root = Path(_cdb.__path__[0])
ADDED_FILES.append((str(_cdb_root / "migrations"), "chromadb/migrations"))
ADDED_FILES.append((str(_cdb_root / "proto"), "chromadb/proto"))

if IS_MAC:
    WEBVIEW_BACKENDS = ["webview.platforms.cocoa"]
elif IS_WIN:
    WEBVIEW_BACKENDS = ["webview.platforms.edgechromium", "webview.platforms.winforms"]
else:
    WEBVIEW_BACKENDS = ["webview.platforms.gtk"]

if IS_WIN:
    EXCLUDES += ["webview.platforms.cocoa", "webview.platforms.gtk"]

HIDDEN_IMPORTS = [
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
    "webview", *WEBVIEW_BACKENDS,
    "chromadb", "chromadb.config",
    "chromadb.segment.impl.metadata.sqlite",
    "chromadb.segment.impl.vector.local_hnsw",
    "chromadb.segment.impl.vector.local_persistent_hnsw",
    *chromadb_hidden,
    "onnxruntime", "onnxruntime.capi",
    "transformers", "transformers.models.bert.tokenization_bert",
    "tokenizers",
    "jieba", "bm25s",
    "openpyxl", "docx", "pdfplumber", "pptx", "bs4",
    "sqlite3", "_sqlite3",
    "pandas", "numpy",
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

if IS_MAC:
    exe = EXE(
        pyz, A.scripts, [], [], [],
        name="HyperFind_bootstrap",
        debug=False, strip=False, upx=True, console=False,
        argv_emulation=True,
    )
    coll = COLLECT(
        exe, A.binaries, A.datas,
        strip=False, upx=True, name="HyperFind",
    )
    app = BUNDLE(
        coll,
        name="HyperFind.app",
        icon="assets/icon.icns" if Path("assets/icon.icns").exists() else None,
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
    # COLLECT+BUNDLE 把 webview JS 放到 Resources/ 但 pywebview 在 MacOS/ 查找
    import shutil as _shutil
    _macos_js = PROJECT_ROOT / "dist" / "HyperFind.app" / "Contents" / "MacOS" / "webview"
    _resources_js = PROJECT_ROOT / "dist" / "HyperFind.app" / "Contents" / "Resources" / "webview"
    if _resources_js.exists() and not _macos_js.exists():
        _shutil.copytree(str(_resources_js), str(_macos_js))
        print("  -> Copied webview/js to MacOS/ for COLLECT compatibility")

elif IS_WIN:
    exe = EXE(
        pyz, A.scripts, A.binaries, A.datas, [],
        name="HyperFind",
        debug=False, strip=False, upx=True, console=False,
        argv_emulation=True,
    )

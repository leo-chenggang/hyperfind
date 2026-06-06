# HyperFind

**本地文件管理与智能搜索桌面应用** — 完全离线，一行命令构建，双击即用。

[![macOS](https://img.shields.io/badge/macOS-11%2B-brightgreen)](https://github.com/leo-chenggang/hyperfind)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 功能

| 板块 | 功能 | 说明 |
|------|------|------|
| **上传中心** | 文件导入 | 拖拽/选择上传，六阶段进度条，硬链接优先不占额外空间 |
| **文件仓库** | 文件管理 | 按类型（Excel/Word/PDF/PPT/HTML/Markdown）分组浏览，一键删除级联清理 |
| **混合搜索** | 内容检索 | BM25 关键词 + 向量语义 + RRF 融合，结果按文件分组高亮 |

支持格式：`.xlsx` `.xls` `.csv` `.docx` `.pdf` `.pptx` `.html` `.htm` `.md`

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面窗口 | [pywebview 6.x](https://pywebview.flowrl.com/)（原生 WKWebView，非 Electron） |
| 前端 | Vanilla HTML/CSS/JS（无框架依赖） |
| 向量搜索 | ChromaDB 0.5 + ONNX MiniLM（INT8 量化，113MB，完全离线） |
| 关键词搜索 | bm25s + jieba 中文分词 |
| 结果融合 | RRF (k=60) |
| 文件解析 | openpyxl · python-docx · pdfplumber · python-pptx · BeautifulSoup4 · mistune |
| 打包 | PyInstaller 6.x（单文件 EXE + 持久缓存目录，首次构建含预热） |

---

## 快速开始

### 下载（macOS）

从 [Releases](https://github.com/leo-chenggang/hyperfind/releases) 下载 `HyperFind.app.zip`，解压后拖入 `/Applications`。

首次启动约需 30-60 秒（系统审核原生库），后续启动 < 5 秒。

### 开发构建

```bash
git clone git@github.com:leo-chenggang/hyperfind.git
cd hyperfind
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**ONNX 模型准备**（首次构建需要，模型目录已在 `.gitignore`）：

```bash
optimum-cli export onnx \
    --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
    models/multilingual-minilm/ \
    --task sentence-similarity

# INT8 量化（448MB → 113MB）
python3 -c "
from onnxruntime.quantization import quantize_dynamic, QuantType
quantize_dynamic('models/multilingual-minilm/model.onnx',
                 'models/multilingual-minilm/model_int8.onnx',
                 weight_type=QuantType.QInt8)
"
```

**打包**：

```bash
bash build_mac.sh
```

构建流程：PyInstaller 打包 → ad-hoc codesign → 首次启动预热（预审核所有原生库）→ 输出 `dist/HyperFind.app`（~186MB）。

### 开发模式运行

```bash
source .venv/bin/activate
python main.py
```

---

## 启动流程

```
双击 App
  ↓
窗口瞬间显示（内嵌启动画面，零文件 I/O）
  ↓
后台初始化引擎（带进度条）
  10%  连接数据库...
  40%  启动搜索引擎...
  70%  加载混合搜索引擎...
  100% 加载界面...
  ↓
自动切换到完整前端界面
```

---

## 架构

```
┌──────────────────────────────────────────────────────────┐
│              pywebview 桌面窗口                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │        Frontend (Vanilla HTML/CSS/JS)              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │  │
│  │  │  上传中心  │  │  文件仓库  │  │    智能搜索    │   │  │
│  │  └─────┬─────┘  └────┬─────┘  └───────┬───────┘   │  │
│  │        └──────────────┼───────────────┘            │  │
│  │              pywebview.api.xxx()                   │  │
│  └───────────────────────┼────────────────────────────┘  │
│  ┌───────────────────────┼────────────────────────────┐  │
│  │              Backend (Python)                      │  │
│  │  ┌────────────────────┴─────────────────────────┐  │  │
│  │  │           API Layer (main.py)                 │  │  │
│  │  └────┬───────────┬──────────┬───────────────────┘  │  │
│  │       │           │          │                       │  │
│  │  ┌────▼────┐ ┌────▼───┐ ┌───▼──────────────┐       │  │
│  │  │ Upload  │ │ File   │ │ Search Engine     │       │  │
│  │  │ Engine  │ │ Repo   │ │ BM25 + ChromaDB   │       │  │
│  │  └─────────┘ └────────┘ └───────────────────┘       │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
hyperfind/
├── main.py                    # 入口：pywebview + API 桥接 + 启动画面
├── app.spec                   # PyInstaller 打包配置（单文件 + 缓存目录）
├── build_mac.sh               # macOS 构建脚本（打包 + 签名 + 预热）
├── requirements.txt           # Python 依赖
├── backend/
│   ├── config.py              # 应用配置（数据目录 ~/Library/...）
│   ├── database.py            # SQLite 元数据库（WAL 模式）
│   ├── cleaner.py             # 退出时缓存清理
│   ├── upload/
│   │   ├── engine.py          # 上传引擎（单线程顺序 + BM25 延迟重建）
│   │   └── link_manager.py    # 五级文件链接策略
│   ├── parsers/
│   │   ├── dispatcher.py      # 格式路由
│   │   ├── excel_parser.py    # .xlsx/.xls/.csv
│   │   ├── word_parser.py     # .docx
│   │   ├── pdf_parser.py      # .pdf
│   │   ├── ppt_parser.py      # .pptx
│   │   ├── html_parser.py     # .html/.htm
│   │   └── markdown_parser.py # .md
│   ├── indexer/
│   │   ├── chunker.py         # 文本切片（512 token / 128 overlap）
│   │   ├── embedder.py        # ONNX 嵌入器（懒加载，384 维）
│   │   ├── vector_store.py    # ChromaDB 向量存储
│   │   └── bm25_store.py      # BM25 关键词索引（延迟重建）
│   └── search/
│       ├── engine.py          # 混合搜索引擎（RRF 融合）
│       ├── highlighter.py     # 搜索高亮 + 摘要提取
│       └── exporter.py        # 匹配文件批量导出
├── frontend/
│   ├── index.html             # 主页面（含 loading overlay）
│   ├── css/app.css            # 样式
│   └── js/app.js              # 前端控制器（事件总线 + API 桥接）
├── models/
│   └── multilingual-minilm/   # ONNX 模型（INT8，113MB，gitignore）
└── assets/
    └── icon.png               # 应用图标（构建时自动转为 .icns）
```

---

## 文件存储策略

五级回退链，按优先级：

1. **硬链接** (hardlink) — 同卷零拷贝，共享 inode
2. **软链接** (symlink) — 跨卷可用
3. **APFS clonefile** — macOS 写时复制，近似零拷贝
4. **分块复制** (chunked) — 8MB 块避免大文件阻塞
5. **普通复制** — 最后手段

数据存储于 `~/Library/Application Support/HyperFind/`，退出时自动清理临时缓存。

---

## License

MIT

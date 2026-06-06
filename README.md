# HyperFind

**本地文件管理与智能搜索桌面应用** — 完全离线，一键安装。

[![macOS](https://img.shields.io/badge/macOS-11%2B-brightgreen)](https://github.com/leo-chenggang/hyperfind)
[![Windows](https://img.shields.io/badge/Windows-10%2B-blue)](https://github.com/leo-chenggang/hyperfind)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)

---

## 功能

| 板块 | 功能 | 说明 |
|------|------|------|
| **上传中心** | 文件导入 | 拖拽/选择上传，实时百分比进度，硬链接优先不占空间 |
| **文件仓库** | 文件管理 | 按类型分组浏览，一键删除级联清理 |
| **智能搜索** | 内容检索 | BM25 + 向量 + RRF 混合搜索，结果按文件分组高亮 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面窗口 | [pywebview 6.x](https://pywebview.flowrl.com/) |
| 向量搜索 | ChromaDB 0.5 + ONNX MiniLM (INT8, 113MB) |
| 关键词搜索 | bm25s + jieba 中文分词 |
| 结果融合 | RRF (k=60, Cormack et al. 2009) |
| 文件解析 | openpyxl · python-docx · pdfplumber · python-pptx · BeautifulSoup4 · mistune |
| 打包 | PyInstaller 6.x (UPX 压缩) |

## 快速开始

### 下载安装

**[Releases](https://github.com/leo-chenggang/hyperfind/releases)** 下载对应平台安装包：

- **macOS**: 下载 `HyperFind.dmg`，拖入 Applications
- **Windows**: 下载 `HyperFind_Setup.exe`，运行安装向导

### 开发构建

```bash
git clone git@github.com:leo-chenggang/hyperfind.git
cd hyperfind
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 导出 ONNX 模型（首次构建需要）
optimum-cli export onnx \
    --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
    models/multilingual-minilm/ \
    --task sentence-similarity

# INT8 量化
python3 -c "
from onnxruntime.quantization import quantize_dynamic, QuantType
quantize_dynamic('models/multilingual-minilm/model.onnx',
                 'models/multilingual-minilm/model_int8.onnx',
                 weight_type=QuantType.QInt8)
"

# 打包
PYTHONNOUSERSITE=1 pyinstaller app.spec --clean --noconfirm
```

### 运行（开发模式）

```bash
source .venv/bin/activate
python main.py
```

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

## 项目结构

```
hyperfind/
├── main.py                    # 入口: pywebview + API 桥接
├── app.spec                   # PyInstaller 打包配置
├── requirements.txt           # Python 依赖
├── backend/
│   ├── config.py              # 应用配置
│   ├── database.py            # SQLite 元数据库 (WAL)
│   ├── cleaner.py             # 退出缓存清理
│   ├── upload/
│   │   ├── engine.py          # 上传引擎 (单线程顺序处理)
│   │   └── link_manager.py    # 五级文件链接策略
│   ├── parsers/               # 6 大格式解析器
│   │   ├── dispatcher.py
│   │   ├── excel_parser.py
│   │   ├── word_parser.py
│   │   ├── pdf_parser.py
│   │   ├── ppt_parser.py
│   │   ├── html_parser.py
│   │   └── markdown_parser.py
│   ├── indexer/
│   │   ├── chunker.py         # 文本切片器 (512/128)
│   │   ├── embedder.py        # ONNX 嵌入器 (384维)
│   │   ├── vector_store.py    # ChromaDB 向量存储
│   │   └── bm25_store.py      # BM25 关键词索引
│   └── search/
│       ├── engine.py          # 混合搜索引擎 (RRF)
│       ├── highlighter.py     # 高亮 + 摘要提取
│       └── exporter.py        # 匹配文件导出
├── frontend/
│   ├── index.html             # 主页面
│   ├── css/app.css            # 硅谷冷淡风样式
│   └── js/app.js              # 前端控制器
├── models/
│   └── multilingual-minilm/   # ONNX 模型 (INT8, 113MB)
└── assets/
    └── icon.png               # 应用图标
```

## 文件存储策略

五级回退链，优先级：

1. **硬链接** (hardlink) — 同卷零拷贝，共享 inode
2. **软链接** (symlink) — 跨卷可用
3. **APFS clonefile** — macOS 写时复制，近似零拷贝
4. **分块复制** (chunked) — 8MB 块避免大文件阻塞
5. **普通复制** (copy) — 最后手段

数据存储于 `~/Library/Application Support/HyperFind/`，退出时仅清空临时缓存。

## License

MIT

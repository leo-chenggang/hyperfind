# HyperFind — 环境与依赖修复指南

> **生成日期**: 2026-05-26
> **审计基线**: Python 3.9.6 / macOS 26.5 (ARM64) / .venv at `/Users/cg/workspace/hyperfind/.venv`
> **前提**: 本指南仅涉及依赖和环境修复，**不涉及代码改动**。

---

## 总览

| 类别 | 数量 | 严重程度 |
|------|------|---------|
| 必须安装 | 1 | 🔴 |
| 强烈建议卸载（冗余） | 4 | 🟠 |
| 建议更新文件 | 1 | 🟡 |
| 可选安装 | 1 | ⚪ |

---

## Step 1 — 安装缺失依赖

### 1.1 安装 PyInstaller（打包必需）

```bash
cd /Users/cg/workspace/hyperfind
.venv/bin/pip install pyinstaller==6.6.0
```

**验证**:
```bash
.venv/bin/pip show pyinstaller | grep Version
# 预期: Version: 6.6.0
```

> **说明**: `optimum[onnxruntime]` 当前代码未使用，暂不安装。如需安装，见 Step 4。

---

## Step 2 — 清理冗余依赖（防止构建膨胀）

这些包不是 HyperFind 的依赖，但被打包进 .venv（可能来自其他项目的污染）。如果不卸载，PyInstaller 打包后体积会从 ~180MB 膨胀到 **2GB+**。

### 2.1 卸载 torch（最大冗余，~2GB）

```bash
.venv/bin/pip uninstall torch -y
```

**验证**:
```bash
.venv/bin/python -c "import torch" 2>&1
# 预期: ModuleNotFoundError: No module named 'torch'
```

### 2.2 卸载 sentence-transformers

```bash
.venv/bin/pip uninstall sentence-transformers -y
```

**验证**:
```bash
.venv/bin/pip show sentence-transformers 2>&1
# 预期: WARNING: Package(s) not found: sentence-transformers
```

### 2.3 卸载 scikit-learn（未使用）

```bash
.venv/bin/pip uninstall scikit-learn -y
```

### 2.4 卸载 scipy（未使用）

```bash
.venv/bin/pip uninstall scipy -y
```

### 2.5 卸载 markitdown（PyPI 空壳）

```bash
.venv/bin/pip uninstall markitdown -y
```

> 这是 PyPI 上 0.0.1a1 空壳包，不是真正的 markitdown。如果代码中需要 markitdown，应安装 `markitdown[all]`。

### 2.6 批量验证卸载结果

```bash
.venv/bin/pip list 2>/dev/null | grep -iE "torch|sentence-transformers|scikit-learn|scipy|markitdown"
# 预期: 无输出
```

### 2.7 卸载后再次检查依赖完整性

```bash
.venv/bin/pip check
# 预期: No broken requirements found.
```

---

## Step 3 — 更新 requirements.txt

当前 `requirements.txt` 版本远低于实际安装版本。锁定当前版本避免将来降级。

### 3.1 生成新的 requirements.txt

```bash
cd /Users/cg/workspace/hyperfind

# 备份旧文件
cp requirements.txt requirements.txt.bak

# 只冻结核心依赖（排除 setuptools/pip/wheel 等工具包）
.venv/bin/pip freeze | grep -vE "^(pip|setuptools|wheel)=" | grep -v "^-e " > requirements.txt
```

### 3.2 检查新文件

```bash
cat requirements.txt
```

确认包含以下核心包且版本正确：

| 包 | 应出现的版本 |
|----|------------|
| pywebview | 6.1 |
| chromadb | 0.5.0 |
| onnxruntime | 1.19.2 |
| transformers | 4.57.6 |
| bm25s | 0.3.9 |
| jieba | 0.42.1 |
| openpyxl | 3.1.5 |
| python-docx | 1.2.0 |
| pdfplumber | 0.11.8 |
| python-pptx | 1.0.2 |
| beautifulsoup4 | 4.14.3 |
| mistune | 3.2.1 |
| numpy | 1.26.4 |
| pandas | 2.3.3 |
| pyinstaller | 6.6.0 |

---

## Step 4 — 可选：安装 optimum（ONNX 模型导出）

如果将来需要从 HuggingFace 模型导出 ONNX 格式（如换用其他嵌入模型），安装此包：

```bash
.venv/bin/pip install optimum[onnxruntime]==1.17.0
```

当前阶段不需要。HyperFind 直接使用已有的 `model.onnx`。

---

## Step 5 — 最终验证（全部通过才算完成）

### 5.1 依赖完整性

```bash
cd /Users/cg/workspace/hyperfind
.venv/bin/pip check
# 预期: No broken requirements found.
```

### 5.2 核心模块导入

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from backend.config import AppConfig; print('config: OK')
from backend.database import Database; print('database: OK')
from backend.indexer.embedder import ONNXEmbedder; print('embedder: OK')
from backend.indexer.chunker import TextChunker; print('chunker: OK')
from backend.indexer.bm25_store import BM25Store; print('bm25: OK')
from backend.indexer.vector_store import VectorStore; print('chroma: OK')
from backend.upload.link_manager import link_file; print('link: OK')
from backend.upload.engine import ConcurrentUploadEngine; print('engine: OK')
from backend.parsers.dispatcher import parse_file; print('parser: OK')
print('ALL MODULES OK')
"
```

### 5.3 ONNX 模型推理

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from backend.indexer.embedder import ONNXEmbedder
from pathlib import Path
import numpy as np
e = ONNXEmbedder(Path('models/multilingual-minilm'))
e.load()
v = e.encode(['测试中文','Hello world'])
print(f'Shape: {v.shape}')  # 预期: (2, 384)
print(f'Norm: {np.linalg.norm(v[0]):.4f}')  # 预期: ~1.0
print('ONNX: OK')
"
```

### 5.4 PyInstaller 可用

```bash
.venv/bin/pyinstaller --version
# 预期: 6.6.0
```

### 5.5 冗余确认

```bash
.venv/bin/pip list 2>/dev/null | grep -iE "torch|sentence-transformers|scikit-learn|scipy"
# 预期: 无输出
```

---

## 修复后状态

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 缺失依赖 | 1 (pyinstaller) | 0 |
| 冗余大包 | torch 2.8.0 等 ~4 个 | 0 |
| requirements.txt | 10 个版本落后 | 全部锁定 |
| 预计打包体积 | 2GB+ | ~180MB |
| pip check | ✅ | ✅ |

---

## 非阻塞已知项（可忽略）

| 问题 | 说明 |
|------|------|
| urllib3 + LibreSSL 警告 | macOS Python 使用 LibreSSL，urllib3 警告但不影响功能（HyperFind 不联网） |
| Python 3.9 EOL | 所有当前依赖仍支持，长期建议升级到 3.11+，但不阻塞 Phase 2 |
| ChromaDB 自带 fastapi/uvicorn | 是 ChromaDB 的依赖，非 HyperFind 直接使用，但无法卸载 |

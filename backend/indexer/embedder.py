"""
ONNX 嵌入器 — 使用 MiniLM 模型将文本转为 384 维向量
完全离线，INT8 量化模型，~15ms/条
"""

import threading
from pathlib import Path
from typing import Optional


def _get_np():
    """惰性导入 numpy（避免模块级导入失败）"""
    import numpy
    return numpy


class ONNXEmbedder:
    """ONNX Runtime 文本嵌入器"""

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / "model.onnx"
        self._session: Optional[object] = None
        self._tokenizer: Optional[object] = None
        self._lock = threading.RLock()
        self.is_loaded = False

    def load(self) -> None:
        """加载 ONNX 模型和分词器"""
        with self._lock:
            if self.is_loaded:
                return

            from transformers import AutoTokenizer
            import onnxruntime as ort

            self._tokenizer = AutoTokenizer.from_pretrained(
                str(self.model_dir), fix_mistral_regex=True
            )

            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4

            self._session = ort.InferenceSession(
                str(self.model_path), sess_options
            )

            # Warmup
            self._warmup()
            self.is_loaded = True

    def _warmup(self):
        """内联预热 — 不通过公共 API（避免 RLock 重入死锁）"""
        np = _get_np()
        inputs = self._tokenizer(
            ["warmup"], padding=True, truncation=True, max_length=512,
            return_tensors="np",
        )
        outputs = self._session.run(None, dict(inputs))
        token_embeddings = outputs[0]
        attention_mask = inputs["attention_mask"][:, :, np.newaxis].astype(np.float32)
        embeddings = np.sum(token_embeddings * attention_mask, axis=1) / np.maximum(
            np.sum(attention_mask, axis=1), 1e-8
        )
        embeddings = embeddings / np.maximum(np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8)

    def get_embedder(self):
        """获取或创建嵌入器实例（加载锁保护）"""
        with self._lock:
            if not self.is_loaded:
                self.load()
            return self

    def encode(self, texts: list[str], batch_size: int = 32):
        """将文本批量编码为向量，返回 (n, 384) float32 numpy 数组"""
        self.get_embedder()
        np = _get_np()

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            inputs = self._tokenizer(
                batch, padding=True, truncation=True, max_length=512,
                return_tensors="np",
            )
            outputs = self._session.run(None, dict(inputs))
            token_embeddings = outputs[0]
            attention_mask = inputs["attention_mask"][:, :, np.newaxis].astype(np.float32)

            embeddings = np.sum(token_embeddings * attention_mask, axis=1) / np.maximum(
                np.sum(attention_mask, axis=1), 1e-8
            )
            embeddings = embeddings / np.maximum(
                np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8
            )
            all_embeddings.append(embeddings.astype(np.float32))

        if not all_embeddings:
            return np.empty((0, 384), dtype=np.float32)

        return np.vstack(all_embeddings)

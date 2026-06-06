"""
ONNX 嵌入器 — MiniLM 模型将文本转为 384 维向量
完全离线，INT8 量化模型，~15ms/条。
使用 threading.RLock 避免重入死锁。
"""

import threading
from pathlib import Path
from typing import Optional


class ONNXEmbedder:
    """ONNX Runtime 文本嵌入器 — 线程安全"""

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.model_path: Path = self.model_dir / "model.onnx"
        self._session: Optional[object] = None
        self._tokenizer: Optional[object] = None
        self._lock = threading.RLock()
        self.is_loaded: bool = False

    def load(self) -> None:
        """加载 ONNX 模型和分词器（线程安全）"""
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
            self._session = ort.InferenceSession(str(self.model_path), sess_options)

            self._warmup_inline()
            self.is_loaded = True

    def _warmup_inline(self) -> None:
        """内联预热 — 不通过公共 encode() 避免 RLock 重入死锁"""
        import numpy as np

        inputs = self._tokenizer(
            ["warmup"], padding=True, truncation=True, max_length=512,
            return_tensors="np",
        )
        outputs = self._session.run(None, dict(inputs))
        token_emb = outputs[0]
        mask = inputs["attention_mask"][:, :, np.newaxis].astype(np.float32)
        emb = np.sum(token_emb * mask, axis=1) / np.maximum(np.sum(mask, axis=1), 1e-8)
        emb = emb / np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-8)

    def get_embedder(self) -> "ONNXEmbedder":
        """获取或创建嵌入器实例（加载锁保护）"""
        with self._lock:
            if not self.is_loaded:
                self.load()
            return self

    def encode(self, texts: list[str], batch_size: int = 32):
        """批量编码文本为向量，返回 (n, 384) float32 numpy 数组"""
        self.get_embedder()
        import numpy as np

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            inputs = self._tokenizer(
                batch, padding=True, truncation=True, max_length=512,
                return_tensors="np",
            )
            outputs = self._session.run(None, dict(inputs))
            token_emb = outputs[0]
            attention_mask = inputs["attention_mask"][:, :, np.newaxis].astype(np.float32)

            emb = np.sum(token_emb * attention_mask, axis=1) / np.maximum(
                np.sum(attention_mask, axis=1), 1e-8
            )
            emb = emb / np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-8)
            all_embeddings.append(emb.astype(np.float32))

        if not all_embeddings:
            return np.empty((0, 384), dtype=np.float32)
        return np.vstack(all_embeddings)

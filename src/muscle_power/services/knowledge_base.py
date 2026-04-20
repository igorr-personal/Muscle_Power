"""Knowledge base with semantic search using SentenceTransformers (optional)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from muscle_power.utils.logger import get_logger, log_action

_log = get_logger(__name__)

try:
    from sentence_transformers import SentenceTransformer  # type: ignore[import]
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False


class KnowledgeBase:
    """
    RAG pipeline that indexes documents from a folder and supports
    semantic search via cosine similarity.
    Falls back to TF-IDF keyword matching when SentenceTransformers is absent.
    """

    def __init__(
        self,
        documents_dir: str = "documents",
        index_dir: str = "kb_data",
        model_name: str = "all-mpnet-base-v2",
        top_k: int = 5,
    ) -> None:
        self._docs_dir = Path(documents_dir)
        self._index_dir = Path(index_dir)
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._model_name = model_name
        self._top_k = top_k
        self._model: Any = None
        self._chunks: list[str] = []
        self._embeddings: np.ndarray | None = None
        self._meta: list[dict[str, Any]] = []
        self._index_path = self._index_dir / "index.json"
        self._load_index()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _get_model(self) -> Any:
        if not ST_AVAILABLE:
            return None
        if self._model is None:
            _log.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _chunk_text(self, text: str, min_len: int = 500, max_len: int = 1500) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) < max_len:
                current = f"{current}\n\n{para}".strip()
            else:
                if len(current) >= min_len:
                    chunks.append(current)
                current = para
        if current and len(current) >= min_len:
            chunks.append(current)
        return chunks or [text[:max_len]]

    def index_documents(self) -> int:
        """Ingest all supported files from documents_dir. Returns chunk count."""
        if not self._docs_dir.exists():
            self._docs_dir.mkdir(parents=True, exist_ok=True)
            return 0

        all_chunks: list[str] = []
        all_meta: list[dict[str, Any]] = []

        for fp in sorted(self._docs_dir.rglob("*")):
            if fp.suffix.lower() not in {".txt", ".md", ".csv", ".json"}:
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                _log.warning("Cannot read %s: %s", fp, exc)
                continue
            chunks = self._chunk_text(text)
            for chunk in chunks:
                all_chunks.append(chunk)
                all_meta.append({"filename": fp.name, "doc_type": self._infer_type(fp)})

        if not all_chunks:
            return 0

        model = self._get_model()
        if model is not None:
            embeddings = model.encode(all_chunks, show_progress_bar=False)
            self._embeddings = np.array(embeddings, dtype=np.float32)
        else:
            # Fallback: simple TF-IDF bag-of-words vectors
            self._embeddings = self._tfidf_vectors(all_chunks)

        self._chunks = all_chunks
        self._meta = all_meta
        self._save_index()
        log_action(_log, "kb_indexed", {"chunks": len(all_chunks)})
        return len(all_chunks)

    def _infer_type(self, fp: Path) -> str:
        name = fp.name.lower()
        if "baseline" in name:
            return "baselines"
        if "issue" in name or "bug" in name or "error" in name:
            return "issues"
        return "test-results"

    def _tfidf_vectors(self, texts: list[str]) -> np.ndarray:
        """Simple normalized word-frequency vectors as fallback."""
        vocab: dict[str, int] = {}
        for text in texts:
            for word in re.findall(r"\w+", text.lower()):
                if word not in vocab:
                    vocab[word] = len(vocab)
        vecs = np.zeros((len(texts), len(vocab) or 1), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"\w+", text.lower()):
                if word in vocab:
                    vecs[i, vocab[word]] += 1
            norm = np.linalg.norm(vecs[i])
            if norm > 0:
                vecs[i] /= norm
        return vecs

    def _save_index(self) -> None:
        data = {
            "chunks": self._chunks,
            "meta": self._meta,
            "embeddings": (
                self._embeddings.tolist() if self._embeddings is not None else []
            ),
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._index_path.write_text(json.dumps(data), encoding="utf-8")

    def _load_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            self._chunks = data.get("chunks", [])
            self._meta = data.get("meta", [])
            raw_emb = data.get("embeddings", [])
            self._embeddings = np.array(raw_emb, dtype=np.float32) if raw_emb else None
        except Exception as exc:
            _log.warning("Could not load KB index: %s", exc)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Semantic (or keyword) search. Returns top-k matching chunks."""
        k = top_k or self._top_k
        if not self._chunks or self._embeddings is None:
            return []

        model = self._get_model()
        if model is not None:
            q_emb = model.encode([query])
            q_vec = np.array(q_emb, dtype=np.float32)[0]
        else:
            words = set(re.findall(r"\w+", query.lower()))
            all_words = set()
            for c in self._chunks:
                all_words |= set(re.findall(r"\w+", c.lower()))
            vocab = {w: i for i, w in enumerate(sorted(all_words))}
            q_vec = np.zeros(len(vocab) or 1, dtype=np.float32)
            for w in words:
                if w in vocab:
                    q_vec[vocab[w]] = 1.0
            norm = np.linalg.norm(q_vec)
            if norm > 0:
                q_vec /= norm

        # Cosine similarity
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        safe_norms = np.where(norms == 0, 1e-8, norms)
        normed = self._embeddings / safe_norms
        q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-8)
        scores = normed @ q_norm
        top_indices = np.argsort(scores)[::-1][:k]
        return [
            {
                "chunk": self._chunks[i],
                "score": float(scores[i]),
                "filename": self._meta[i].get("filename", ""),
                "doc_type": self._meta[i].get("doc_type", ""),
            }
            for i in top_indices
            if scores[i] > 0.01
        ]

    def get_stats(self) -> dict[str, Any]:
        return {
            "chunks": len(self._chunks),
            "documents": len({m.get("filename") for m in self._meta}),
            "embedding_model": self._model_name if ST_AVAILABLE else "tfidf-fallback",
            "index_exists": self._index_path.exists(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_kb: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        from muscle_power.utils.config import get_config
        cfg = get_config()
        _kb = KnowledgeBase(
            documents_dir=cfg.kb.documents_dir,
            index_dir=cfg.kb.index_dir,
            model_name=cfg.kb.embedding_model,
            top_k=cfg.kb.top_k,
        )
    return _kb

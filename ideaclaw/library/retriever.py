"""RAG retriever — TF-IDF + BM25 hybrid search over library chunks.

Supports:
  - Pure TF-IDF cosine similarity (zero dependencies)
  - BM25 keyword scoring (zero dependencies)
  - Optional sentence-transformers embeddings (if installed)
  - Hybrid scoring: α * semantic + (1-α) * BM25

Usage:
    retriever = LibraryRetriever(library_dir)
    retriever.build_index()  # Build from all ingested chunks
    results = retriever.search("attention mechanism", top_k=5)
"""

from __future__ import annotations
import logging

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ['RetrievalResult', 'LibraryRetriever']


@dataclass
class RetrievalResult:
    """A single retrieval result."""
    chunk_id: str
    doc_id: str
    text: str
    section: str
    score: float
    method: str        # "tfidf", "bm25", "hybrid", "embedding"
    doc_title: str = ""


class LibraryRetriever:
    """Hybrid TF-IDF + BM25 retriever over library chunks.

    Falls back gracefully:
      1. sentence-transformers available → hybrid (embedding + BM25)
      2. No extra deps → TF-IDF + BM25 hybrid
    """

    BM25_K1 = 1.5
    BM25_B = 0.75
    HYBRID_ALPHA = 0.6   # Weight for semantic (TF-IDF or embedding)

    def __init__(self, library_dir: Optional[Path] = None):
        self.library_dir = library_dir or (Path.home() / ".ideaclaw" / "library")
        self.docs_dir = self.library_dir / "documents"
        self.index_path = self.library_dir / "retrieval_index.json"

        # In-memory index
        self._chunks: List[Dict[str, Any]] = []
        self._doc_titles: Dict[str, str] = {}
        self._tfidf_index: Dict[str, Dict[str, float]] = {}  # chunk_id → term→weight
        self._idf: Dict[str, float] = {}
        self._avg_dl: float = 0.0
        self._doc_lengths: Dict[str, int] = {}

        # Optional embedding model
        self._embedder = None
        self._embeddings: Dict[str, List[float]] = {}
        self._has_embeddings = False

    def build_index(self):
        """Build retrieval index from all ingested documents."""
        self._chunks = []
        self._doc_titles = {}

        if not self.docs_dir.exists():
            return

        # Load all chunks
        for doc_file in sorted(self.docs_dir.glob("*.json")):
            try:
                data = json.loads(doc_file.read_text(encoding="utf-8"))
                doc_id = data.get("id", doc_file.stem)
                self._doc_titles[doc_id] = data.get("title", doc_file.stem)

                for chunk in data.get("chunks", []):
                    chunk["doc_title"] = self._doc_titles[doc_id]
                    self._chunks.append(chunk)
            except (json.JSONDecodeError, OSError):
                continue

        if not self._chunks:
            return

        # Build TF-IDF index
        self._build_tfidf()

        # Try loading embeddings
        self._try_load_embeddings()

    def search(
        self,
        query: str,
        top_k: int = 5,
        method: str = "hybrid",
    ) -> List[RetrievalResult]:
        """Search for relevant chunks.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            method: "tfidf", "bm25", "hybrid", or "embedding".

        Returns:
            List of RetrievalResult, sorted by relevance.
        """
        if not self._chunks:
            self.build_index()
        if not self._chunks:
            return []

        if method == "tfidf":
            scores = self._score_tfidf(query)
        elif method == "bm25":
            scores = self._score_bm25(query)
        elif method == "embedding" and self._has_embeddings:
            scores = self._score_embedding(query)
        else:
            # Hybrid: combine TF-IDF (or embedding) + BM25
            if self._has_embeddings:
                semantic_scores = self._score_embedding(query)
            else:
                semantic_scores = self._score_tfidf(query)
            bm25_scores = self._score_bm25(query)

            scores = {}
            all_ids = set(semantic_scores.keys()) | set(bm25_scores.keys())
            for cid in all_ids:
                s = semantic_scores.get(cid, 0.0)
                b = bm25_scores.get(cid, 0.0)
                scores[cid] = self.HYBRID_ALPHA * s + (1 - self.HYBRID_ALPHA) * b
            method = "hybrid"

        # Sort and return top_k
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]

        results = []
        chunk_map = {c["id"]: c for c in self._chunks}
        for chunk_id, score in ranked:
            if score <= 0:
                continue
            chunk = chunk_map.get(chunk_id, {})
            results.append(RetrievalResult(
                chunk_id=chunk_id,
                doc_id=chunk.get("doc_id", ""),
                text=chunk.get("text", ""),
                section=chunk.get("section", ""),
                score=score,
                method=method,
                doc_title=chunk.get("doc_title", ""),
            ))

        return results

    def format_for_prompt(self, results: List[RetrievalResult]) -> str:
        """Format retrieval results as context for LLM prompt injection."""
        if not results:
            return ""
        parts = ["## Relevant Reference Material\n"]
        for i, r in enumerate(results, 1):
            parts.append(f"### [{i}] From: {r.doc_title}")
            if r.section:
                parts.append(f"Section: {r.section}")
            parts.append(f"```\n{r.text[:500]}\n```")
            parts.append("")
        return "\n".join(parts)

    # ---- TF-IDF ----

    def _build_tfidf(self):
        """Build TF-IDF index over all chunks."""
        # Compute document frequency
        df: Dict[str, int] = Counter()
        doc_tfs: Dict[str, Dict[str, float]] = {}
        total_length = 0

        for chunk in self._chunks:
            cid = chunk["id"]
            words = self._tokenize(chunk.get("text", ""))
            total_length += len(words)
            self._doc_lengths[cid] = len(words)

            tf = Counter(words)
            total = len(words) or 1
            doc_tfs[cid] = {w: c / total for w, c in tf.items()}

            for w in set(words):
                df[w] += 1

        n_docs = max(len(self._chunks), 1)
        self._avg_dl = total_length / n_docs

        # Compute IDF
        self._idf = {w: math.log((n_docs - count + 0.5) / (count + 0.5) + 1)
                      for w, count in df.items()}

        # Compute TF-IDF
        self._tfidf_index = {}
        for cid, tf in doc_tfs.items():
            self._tfidf_index[cid] = {
                w: tf_val * self._idf.get(w, 0) for w, tf_val in tf.items()
            }

    def _score_tfidf(self, query: str) -> Dict[str, float]:
        """Score chunks by TF-IDF cosine similarity to query."""
        query_words = self._tokenize(query)
        if not query_words:
            return {}

        query_tf = Counter(query_words)
        total = len(query_words)
        query_vec = {w: (c / total) * self._idf.get(w, 0) for w, c in query_tf.items()}

        scores = {}
        for cid, doc_vec in self._tfidf_index.items():
            scores[cid] = self._cosine(query_vec, doc_vec)
        return scores

    # ---- BM25 ----

    def _score_bm25(self, query: str) -> Dict[str, float]:
        """Score chunks by BM25."""
        query_words = self._tokenize(query)
        if not query_words:
            return {}

        scores: Dict[str, float] = {}
        for chunk in self._chunks:
            cid = chunk["id"]
            words = self._tokenize(chunk.get("text", ""))
            tf = Counter(words)
            dl = len(words)

            score = 0.0
            for qw in query_words:
                if qw not in tf:
                    continue
                f = tf[qw]
                idf = self._idf.get(qw, 0)
                numerator = f * (self.BM25_K1 + 1)
                denominator = f + self.BM25_K1 * (1 - self.BM25_B + self.BM25_B * dl / max(self._avg_dl, 1))
                score += idf * numerator / denominator

            if score > 0:
                scores[cid] = score

        # Normalize
        max_score = max(scores.values()) if scores else 1
        return {k: v / max_score for k, v in scores.items()}

    # ---- Embeddings (optional) ----

    def _try_load_embeddings(self):
        """Try to load sentence-transformers for embedding-based search."""
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            self._has_embeddings = True

            # Compute embeddings for all chunks
            texts = [c.get("text", "")[:512] for c in self._chunks]
            ids = [c["id"] for c in self._chunks]
            embs = self._embedder.encode(texts, show_progress_bar=False)
            self._embeddings = {cid: emb.tolist() for cid, emb in zip(ids, embs)}
        except ImportError:
            self._has_embeddings = False

    def _score_embedding(self, query: str) -> Dict[str, float]:
        """Score chunks by embedding cosine similarity."""
        if not self._embedder or not self._embeddings:
            return self._score_tfidf(query)

        query_emb = self._embedder.encode([query[:512]], show_progress_bar=False)[0]
        scores = {}
        for cid, doc_emb in self._embeddings.items():
            scores[cid] = self._cosine_lists(query_emb.tolist(), doc_emb)
        return scores

    # ---- Helpers ----

    STOPWORDS = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and",
        "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "will", "would", "could", "should",
        "this", "that", "with", "from", "by", "as", "or", "but", "not",
    }

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if w not in cls.STOPWORDS and len(w) > 1]

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        common = set(a.keys()) & set(b.keys())
        if not common:
            return 0.0
        dot = sum(a[k] * b[k] for k in common)
        mag_a = math.sqrt(sum(v ** 2 for v in a.values()))
        mag_b = math.sqrt(sum(v ** 2 for v in b.values()))
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

    @staticmethod
    def _cosine_lists(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x ** 2 for x in a))
        mag_b = math.sqrt(sum(x ** 2 for x in b))
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

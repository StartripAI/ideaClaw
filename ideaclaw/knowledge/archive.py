"""Knowledge archive — stores lessons and reusable insights across runs.

Upgraded with:
  - TF-IDF semantic retrieval (same approach as memory.py)
  - Time-decay weighting (recent entries rank higher)
  - Consolidation (merge overlapping entries)
  - Formatted context generation for prompt injection

Adapted from AutoResearchClaw's metaclaw_bridge concept.
"""

from __future__ import annotations
import logging

import json
import math
import re
import datetime as dt
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ['KnowledgeEntry', 'KnowledgeArchive']


@dataclass
class KnowledgeEntry:
    """A single knowledge entry from a pipeline run."""
    run_id: str
    idea_text: str
    pack_type: str
    key_findings: List[str] = field(default_factory=list)
    counterarguments: List[str] = field(default_factory=list)
    sources_used: List[Dict[str, str]] = field(default_factory=list)
    pqs_score: float = 0.0
    verdict: str = ""
    profile_id: str = ""
    created_at: str = ""
    tags: List[str] = field(default_factory=list)
    # New: decay/strength fields
    strength: float = 1.0
    access_count: int = 0
    last_accessed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KnowledgeEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class KnowledgeArchive:
    """Persistent knowledge archive with semantic retrieval and time decay.

    Stores key findings, counterarguments, sources, and quality metrics
    in a JSON-based archive with TF-IDF retrieval for past runs.
    """

    DECAY_RATE = 0.03        # 3% per day
    MIN_STRENGTH = 0.1
    REINFORCE_BOOST = 0.2

    def __init__(self, archive_dir: Optional[Path] = None):
        self.archive_dir = archive_dir or (Path.home() / ".ideaclaw" / "knowledge")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.archive_dir / "index.json"

    def store(self, entry: KnowledgeEntry) -> Path:
        """Store a knowledge entry.

        Args:
            entry: Knowledge entry from a pipeline run.

        Returns:
            Path to the stored entry file.
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if not entry.created_at:
            entry.created_at = now
        if not entry.last_accessed:
            entry.last_accessed = now

        entry_path = self.archive_dir / f"{entry.run_id}.json"
        entry_path.write_text(
            json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self._update_index(entry)
        return entry_path

    def retrieve_similar(
        self,
        idea_text: str,
        max_results: int = 5,
        category: Optional[str] = None,
    ) -> List[KnowledgeEntry]:
        """Retrieve knowledge entries similar to the given idea.

        Uses TF-IDF cosine similarity with time-decay weighting.
        """
        index = self._load_index()
        entries_meta = index.get("entries", [])

        if category:
            entries_meta = [e for e in entries_meta
                           if e.get("profile_id", "") == category
                           or category in e.get("tags", [])]

        if not entries_meta:
            return []

        query_vec = self._tfidf(idea_text)
        scored: List[Tuple[float, Dict[str, Any]]] = []

        for meta in entries_meta:
            doc_text = f"{meta.get('idea_text', '')} {' '.join(meta.get('tags', []))}"
            doc_vec = self._tfidf(doc_text)
            sim = self._cosine(query_vec, doc_vec)

            # Time decay
            strength = meta.get("strength", 1.0)
            try:
                created = dt.datetime.fromisoformat(meta.get("created_at", ""))
                days = (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 86400
                strength *= math.exp(-self.DECAY_RATE * days)
                strength = max(self.MIN_STRENGTH, strength)
            except (ValueError, TypeError):
                pass

            final_score = sim * strength
            if final_score > 0.01:
                scored.append((final_score, meta))

        scored.sort(key=lambda x: -x[0])

        # Load full entries for top matches
        results = []
        for _, meta in scored[:max_results]:
            entry_path = self.archive_dir / f"{meta['run_id']}.json"
            if entry_path.exists():
                try:
                    data = json.loads(entry_path.read_text(encoding="utf-8"))
                    entry = KnowledgeEntry.from_dict(data)
                    # Reinforce access
                    entry.access_count += 1
                    entry.last_accessed = dt.datetime.now(dt.timezone.utc).isoformat()
                    entry.strength = min(1.0, entry.strength + self.REINFORCE_BOOST)
                    entry_path.write_text(
                        json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    results.append(entry)
                except (json.JSONDecodeError, OSError, TypeError):
                    pass

        return results

    def format_context(self, entries: List[KnowledgeEntry]) -> str:
        """Format knowledge entries for prompt injection."""
        if not entries:
            return ""

        parts = ["## Relevant Past Knowledge\n"]
        for i, e in enumerate(entries, 1):
            parts.append(f"### {i}. {e.idea_text[:100]}")
            parts.append(f"Score: {e.pqs_score:.2f} | Profile: {e.profile_id}")
            if e.key_findings:
                parts.append("**Key Findings:**")
                for f in e.key_findings[:3]:
                    parts.append(f"- {f}")
            if e.counterarguments:
                parts.append("**Counterarguments:**")
                for c in e.counterarguments[:2]:
                    parts.append(f"- {c}")
            parts.append("")
        return "\n".join(parts)

    def consolidate(self) -> int:
        """Merge overlapping entries to reduce redundancy.

        Returns number of entries consolidated.
        """
        index = self._load_index()
        entries_meta = index.get("entries", [])
        if len(entries_meta) < 2:
            return 0

        merged = 0
        to_remove = set()

        for i, a in enumerate(entries_meta):
            if i in to_remove:
                continue
            for j, b in enumerate(entries_meta[i + 1:], i + 1):
                if j in to_remove:
                    continue
                a_vec = self._tfidf(a.get("idea_text", ""))
                b_vec = self._tfidf(b.get("idea_text", ""))
                if self._cosine(a_vec, b_vec) > 0.8:
                    # Merge b into a (keep higher score)
                    if b.get("pqs_score", 0) > a.get("pqs_score", 0):
                        a["pqs_score"] = b["pqs_score"]
                    a["tags"] = list(set(a.get("tags", []) + b.get("tags", [])))
                    to_remove.add(j)
                    merged += 1
                    # Remove b's file
                    b_path = self.archive_dir / f"{b['run_id']}.json"
                    if b_path.exists():
                        b_path.unlink()

        if to_remove:
            entries_meta = [e for i, e in enumerate(entries_meta) if i not in to_remove]
            index["entries"] = entries_meta
            index["total_entries"] = len(entries_meta)
            self.index_path.write_text(
                json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8",
            )

        return merged

    def list_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent knowledge entries from the index."""
        index = self._load_index()
        return index.get("entries", [])[:limit]

    def stats(self) -> Dict[str, Any]:
        """Get archive statistics."""
        index = self._load_index()
        entries = index.get("entries", [])
        by_profile = Counter(e.get("profile_id", "unknown") for e in entries)
        avg_score = sum(e.get("pqs_score", 0) for e in entries) / max(len(entries), 1)
        return {
            "total_entries": len(entries),
            "by_profile": dict(by_profile),
            "avg_pqs_score": round(avg_score, 3),
            "total_findings": sum(e.get("finding_count", 0) for e in entries),
        }

    # ---- Internal ----

    @staticmethod
    def _tfidf(text: str) -> Dict[str, float]:
        """Simple TF vector."""
        words = re.findall(r"\w+", text.lower())
        if not words:
            return {}
        counts = Counter(words)
        total = len(words)
        return {w: c / total for w, c in counts.items()}

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        """Cosine similarity between two TF vectors."""
        if not a or not b:
            return 0.0
        common = set(a.keys()) & set(b.keys())
        if not common:
            return 0.0
        dot = sum(a[k] * b[k] for k in common)
        mag_a = math.sqrt(sum(v ** 2 for v in a.values()))
        mag_b = math.sqrt(sum(v ** 2 for v in b.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def _update_index(self, entry: KnowledgeEntry) -> None:
        """Update the index with a new entry."""
        index = self._load_index()
        entries = index.get("entries", [])

        entries = [e for e in entries if e.get("run_id") != entry.run_id]

        entries.insert(0, {
            "run_id": entry.run_id,
            "idea_text": entry.idea_text[:200],
            "pack_type": entry.pack_type,
            "pqs_score": entry.pqs_score,
            "verdict": entry.verdict,
            "profile_id": entry.profile_id,
            "created_at": entry.created_at,
            "tags": entry.tags,
            "finding_count": len(entry.key_findings),
            "source_count": len(entry.sources_used),
            "strength": entry.strength,
        })

        entries = entries[:1000]

        index["entries"] = entries
        index["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        index["total_entries"] = len(entries)

        self.index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8",
        )

    def _load_index(self) -> Dict[str, Any]:
        """Load or create the index file."""
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"entries": [], "total_entries": 0}

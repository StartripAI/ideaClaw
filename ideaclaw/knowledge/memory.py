"""Memory system — cross-session learning from past research runs.

Builds on knowledge/archive.py but adds:
  - Embedding-free semantic retrieval (TF-IDF + cosine)
  - Automatic insight extraction from completed runs
  - Memory consolidation (merge overlapping entries)
  - Context injection into new prompts
  - Forgetting curve (older memories decay unless reinforced)

Usage:
    mem = Memory()
    mem.learn(run_state)          # After a run completes
    context = mem.recall(idea)    # Before a new run starts
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

__all__ = ['MemoryItem', 'RecallResult', 'Memory']


@dataclass
class MemoryItem:
    """A single memory from a research run."""
    id: str
    idea: str
    scenario_id: str
    category: str
    insights: List[str]               # Key learnings
    effective_sources: List[str]      # Sources that proved most useful
    pitfalls: List[str]               # What went wrong
    best_practices: List[str]         # What worked
    final_score: float
    iteration_count: int
    created_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    strength: float = 1.0             # Decay over time, reinforced on access
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryItem":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RecallResult:
    """Result of a memory recall operation."""
    relevant_memories: List[MemoryItem]
    context_prompt: str               # Formatted for prompt injection
    confidence: float                 # 0-1 confidence in relevance


class Memory:
    """Cross-session memory with semantic retrieval and forgetting curve.

    Stores at: ~/.ideaclaw/memory/
    """

    DECAY_RATE = 0.05       # Strength decays 5% per day
    MIN_STRENGTH = 0.1      # Minimum strength before pruning
    REINFORCE_BOOST = 0.3   # Strength boost on access

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = memory_dir or (Path.home() / ".ideaclaw" / "memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = self.memory_dir / "memories.json"
        self._memories: List[MemoryItem] = []
        self._load()

    # ---- Core API ----

    def learn(
        self,
        run_id: str,
        idea: str,
        scenario_id: str,
        category: str,
        insights: List[str],
        effective_sources: Optional[List[str]] = None,
        pitfalls: Optional[List[str]] = None,
        best_practices: Optional[List[str]] = None,
        final_score: float = 0.0,
        iteration_count: int = 0,
        tags: Optional[List[str]] = None,
    ) -> MemoryItem:
        """Learn from a completed research run.

        Args:
            run_id: Unique run identifier.
            idea: The research idea/topic.
            scenario_id: Which scenario profile was used.
            category: Domain category.
            insights: Key findings and learnings.
            effective_sources: Sources that proved most valuable.
            pitfalls: Things that didn't work.
            best_practices: Strategies that worked well.
            final_score: Final quality score.
            iteration_count: How many iterations were needed.
            tags: Optional tags for categorization.

        Returns:
            The created MemoryItem.
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        item = MemoryItem(
            id=run_id,
            idea=idea,
            scenario_id=scenario_id,
            category=category,
            insights=insights,
            effective_sources=effective_sources or [],
            pitfalls=pitfalls or [],
            best_practices=best_practices or [],
            final_score=final_score,
            iteration_count=iteration_count,
            created_at=now,
            last_accessed=now,
            access_count=0,
            strength=1.0,
            tags=tags or [category, scenario_id],
        )

        # Check for duplicate run_id
        self._memories = [m for m in self._memories if m.id != run_id]
        self._memories.append(item)
        self._save()
        return item

    def recall(
        self,
        idea: str,
        category: Optional[str] = None,
        max_results: int = 5,
    ) -> RecallResult:
        """Recall relevant memories for a new research task.

        Uses TF-IDF cosine similarity for semantic matching.
        Applies forgetting curve before scoring.

        Args:
            idea: The new research idea to find context for.
            category: Optional domain filter.
            max_results: Maximum memories to return.

        Returns:
            RecallResult with relevant memories and formatted context.
        """
        self._apply_decay()

        # Filter by category if specified
        candidates = self._memories
        if category:
            candidates = [m for m in candidates if m.category == category]

        if not candidates:
            return RecallResult([], "", 0.0)

        # Score by TF-IDF cosine similarity * memory strength
        scored = []
        query_vec = self._tfidf(idea)
        for mem in candidates:
            doc = f"{mem.idea} {' '.join(mem.insights)} {' '.join(mem.tags)}"
            doc_vec = self._tfidf(doc)
            sim = self._cosine(query_vec, doc_vec) * mem.strength
            scored.append((sim, mem))

        scored.sort(key=lambda x: -x[0])
        top = scored[:max_results]

        # Reinforce accessed memories
        for _, mem in top:
            mem.last_accessed = dt.datetime.now(dt.timezone.utc).isoformat()
            mem.access_count += 1
            mem.strength = min(1.0, mem.strength + self.REINFORCE_BOOST)

        self._save()

        # Filter by minimum relevance threshold
        relevant = []
        max_sim = 0.0
        for sim, mem in top:
            if sim > 0.05:
                relevant.append(mem)
                max_sim = max(max_sim, sim)

        context = self._format_context(relevant)
        return RecallResult(relevant, context, max_sim)

    def forget(self, run_id: str) -> bool:
        """Explicitly forget a memory."""
        before = len(self._memories)
        self._memories = [m for m in self._memories if m.id != run_id]
        if len(self._memories) < before:
            self._save()
            return True
        return False

    def consolidate(self) -> int:
        """Merge overlapping memories to reduce redundancy.

        Returns number of memories consolidated.
        """
        if len(self._memories) < 2:
            return 0

        merged = 0
        to_remove = set()

        for i, a in enumerate(self._memories):
            if i in to_remove:
                continue
            for j, b in enumerate(self._memories[i + 1:], i + 1):
                if j in to_remove:
                    continue
                # Check if same category + high idea overlap
                if a.category == b.category:
                    sim = self._cosine(self._tfidf(a.idea), self._tfidf(b.idea))
                    if sim > 0.8:
                        # Merge b into a
                        a.insights = list(set(a.insights + b.insights))
                        a.effective_sources = list(set(a.effective_sources + b.effective_sources))
                        a.pitfalls = list(set(a.pitfalls + b.pitfalls))
                        a.best_practices = list(set(a.best_practices + b.best_practices))
                        a.strength = max(a.strength, b.strength)
                        a.access_count += b.access_count
                        to_remove.add(j)
                        merged += 1

        if to_remove:
            self._memories = [m for i, m in enumerate(self._memories) if i not in to_remove]
            self._save()

        return merged

    def stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        by_cat = Counter(m.category for m in self._memories)
        return {
            "total_memories": len(self._memories),
            "by_category": dict(by_cat),
            "avg_strength": sum(m.strength for m in self._memories) / max(len(self._memories), 1),
            "total_insights": sum(len(m.insights) for m in self._memories),
            "total_pitfalls": sum(len(m.pitfalls) for m in self._memories),
        }

    # ---- Internal ----

    def _apply_decay(self):
        """Apply forgetting curve: strength decays over time."""
        now = dt.datetime.now(dt.timezone.utc)
        for mem in self._memories:
            if mem.last_accessed:
                try:
                    last = dt.datetime.fromisoformat(mem.last_accessed)
                    days = (now - last).total_seconds() / 86400
                    mem.strength *= math.exp(-self.DECAY_RATE * days)
                    mem.strength = max(self.MIN_STRENGTH, mem.strength)
                except (ValueError, TypeError):
                    pass

        # Prune very weak memories (strength < MIN_STRENGTH * 0.5)
        self._memories = [m for m in self._memories if m.strength >= self.MIN_STRENGTH * 0.5]

    @staticmethod
    def _tfidf(text: str) -> Dict[str, float]:
        """Simple TF vector (no IDF corpus needed for small sets)."""
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

    @staticmethod
    def _format_context(memories: List[MemoryItem]) -> str:
        """Format memories into a context prompt for LLM injection."""
        if not memories:
            return ""

        parts = ["## Relevant Past Research\n"]
        for i, mem in enumerate(memories, 1):
            parts.append(f"### {i}. {mem.idea} ({mem.category}/{mem.scenario_id})")
            parts.append(f"Score: {mem.final_score:.2f} | Iterations: {mem.iteration_count}")
            if mem.insights:
                parts.append("**Key Insights:**")
                for ins in mem.insights[:3]:
                    parts.append(f"- {ins}")
            if mem.best_practices:
                parts.append("**What Worked:**")
                for bp in mem.best_practices[:2]:
                    parts.append(f"- {bp}")
            if mem.pitfalls:
                parts.append("**Pitfalls to Avoid:**")
                for pit in mem.pitfalls[:2]:
                    parts.append(f"- {pit}")
            parts.append("")

        return "\n".join(parts)

    def _load(self):
        """Load memories from disk."""
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text(encoding="utf-8"))
                self._memories = [MemoryItem.from_dict(d) for d in data]
            except (json.JSONDecodeError, OSError):
                self._memories = []

    def _save(self):
        """Persist memories to disk (atomic write via tempfile + rename)."""
        import tempfile as _tf
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = [m.to_dict() for m in self._memories]
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        fd, tmp = _tf.mkstemp(dir=str(self.store_path.parent), suffix=".tmp")
        try:
            import os as _os
            _os.write(fd, payload.encode("utf-8"))
            _os.close(fd)
            _os.replace(tmp, str(self.store_path))
        except OSError:  # noqa: BLE001
            import os as _os
            try:
                _os.close(fd)
            except OSError:
                pass
            if Path(tmp).exists():
                Path(tmp).unlink()
            raise

    # ---- Importance & Stats ----

    @staticmethod
    def importance_score(item: MemoryItem) -> float:
        """Compute composite importance score (0-1).

        Factors:
          - Quality score from original run (40%)
          - Insight count / richness (20%)
          - Access frequency (20%)
          - Recency / strength (20%)
        """
        quality = min(item.final_score, 1.0) * 0.4
        insight_richness = min(len(item.insights) / 5.0, 1.0) * 0.2
        access = min(item.access_count / 10.0, 1.0) * 0.2
        strength = item.strength * 0.2
        return quality + insight_richness + access + strength

    def stats(self) -> Dict[str, Any]:
        """Aggregate memory statistics."""
        if not self._memories:
            return {"total": 0}
        by_cat: Dict[str, int] = {}
        by_scenario: Dict[str, int] = {}
        scores = []
        for m in self._memories:
            by_cat[m.category] = by_cat.get(m.category, 0) + 1
            by_scenario[m.scenario_id] = by_scenario.get(m.scenario_id, 0) + 1
            scores.append(m.final_score)
        return {
            "total": len(self._memories),
            "avg_score": sum(scores) / len(scores),
            "max_score": max(scores),
            "by_category": by_cat,
            "by_scenario": by_scenario,
            "avg_importance": sum(self.importance_score(m) for m in self._memories) / len(self._memories),
        }

    def export_markdown(self) -> str:
        """Export all memories as markdown for review."""
        lines = ["# Memory Bank", f"**Total memories**: {len(self._memories)}", ""]
        ranked = sorted(self._memories, key=self.importance_score, reverse=True)
        for i, m in enumerate(ranked, 1):
            imp = self.importance_score(m)
            lines.append(
                f"### {i}. {m.idea[:60]} "
                f"(importance={imp:.2f}, score={m.final_score:.2f}, strength={m.strength:.2f})"
            )
            lines.append(f"- Category: {m.category} | Scenario: {m.scenario_id}")
            lines.append(f"- Accessed: {m.access_count}× | Created: {m.created_at[:10]}")
            if m.insights:
                lines.append("- **Insights**: " + "; ".join(m.insights[:3]))
            if m.pitfalls:
                lines.append("- **Pitfalls**: " + "; ".join(m.pitfalls[:2]))
            lines.append("")
        return "\n".join(lines)


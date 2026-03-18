"""Knowledge archive — stores lessons and reusable insights across runs.

Adapted from AutoResearchClaw's metaclaw_bridge concept.
Provides cross-run knowledge persistence and retrieval.
"""

from __future__ import annotations

import json
import datetime as dt
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class KnowledgeArchive:
    """Persistent knowledge archive across pipeline runs.

    Stores key findings, counterarguments, sources, and quality metrics
    in a JSON-based archive for retrieval in future runs.
    """

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
        if not entry.created_at:
            entry.created_at = dt.datetime.now(dt.timezone.utc).isoformat()

        # Store individual entry
        entry_path = self.archive_dir / f"{entry.run_id}.json"
        entry_path.write_text(
            json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Update index
        self._update_index(entry)

        return entry_path

    def retrieve_similar(
        self,
        idea_text: str,
        max_results: int = 5,
    ) -> List[KnowledgeEntry]:
        """Retrieve knowledge entries similar to the given idea.

        Uses simple keyword matching for retrieval.
        """
        index = self._load_index()
        query_words = set(idea_text.lower().split())

        scored: List[tuple] = []
        for entry_meta in index.get("entries", []):
            entry_words = set(entry_meta.get("idea_text", "").lower().split())
            overlap = len(query_words & entry_words)
            if overlap > 0:
                scored.append((overlap, entry_meta))

        scored.sort(key=lambda x: -x[0])

        results = []
        for _, meta in scored[:max_results]:
            entry_path = self.archive_dir / f"{meta['run_id']}.json"
            if entry_path.exists():
                data = json.loads(entry_path.read_text(encoding="utf-8"))
                results.append(KnowledgeEntry(**data))

        return results

    def list_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent knowledge entries from the index."""
        index = self._load_index()
        entries = index.get("entries", [])
        return entries[:limit]

    def _update_index(self, entry: KnowledgeEntry) -> None:
        """Update the index with a new entry."""
        index = self._load_index()
        entries = index.get("entries", [])

        # Remove existing entry with same run_id
        entries = [e for e in entries if e.get("run_id") != entry.run_id]

        # Add new entry summary
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
        })

        # Keep last 1000 entries
        entries = entries[:1000]

        index["entries"] = entries
        index["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        index["total_entries"] = len(entries)

        self.index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_index(self) -> Dict[str, Any]:
        """Load or create the index file."""
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"entries": [], "total_entries": 0}

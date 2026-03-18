"""Source registry — trustworthiness tiers for known sources.

Ported from OpenRevise config/source_registry.yaml
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class RegistryEntry:
    """A registered source with reliability metadata."""
    source_id: str
    source_type: str  # literature | practice | regulatory | institution | general | consumer
    tier: str  # S | A | B | C
    country: str = ""
    institution_tier: str = ""
    reliability_rule: str = ""
    alias_keywords: list = None

    def __post_init__(self):
        if self.alias_keywords is None:
            self.alias_keywords = []


class SourceRegistry:
    """Registry of known sources with trustworthiness tiers.

    Extends OpenRevise's medical/academic registry with general and consumer sources.
    """

    def __init__(self, registry_path: Optional[Path] = None):
        self.entries: Dict[str, RegistryEntry] = {}
        if registry_path and registry_path.exists():
            self._load(registry_path)

    def _load(self, path: Path) -> None:
        """Load registry from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry_data in data.get("sources", []):
            entry = RegistryEntry(**entry_data)
            self.entries[entry.source_id] = entry

    def lookup(self, source_id: str) -> Optional[RegistryEntry]:
        """Look up a source by ID."""
        return self.entries.get(source_id)

    def find_by_keyword(self, keyword: str) -> List[RegistryEntry]:
        """Find sources matching a keyword."""
        keyword_lower = keyword.lower()
        return [
            e for e in self.entries.values()
            if keyword_lower in e.source_id.lower()
            or any(keyword_lower in kw.lower() for kw in e.alias_keywords)
        ]

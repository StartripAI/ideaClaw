"""Multi-source collector — web, academic APIs, local files.

TODO: Port and extend from OpenRevise check_revise_sources.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Source:
    """A collected source with metadata."""
    source_id: str
    title: str
    source_type: str  # web | academic | local_pdf | local_docx | local_pptx | local_image
    url: str = ""
    path: str = ""
    snippet: str = ""
    relevance_score: float = 0.0
    quality_score: float = 0.0
    collected_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class SourceCollector:
    """Collects sources from multiple channels."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.search_engines = config.get("search_engines", [])
        self.academic_apis = config.get("academic_apis", [])
        self.local_paths = config.get("local_paths", [])

    def collect(self, queries: List[str]) -> List[Source]:
        """Collect sources from all configured channels.

        TODO: Implement actual collection from:
        - Web search (Google, Bing)
        - Academic APIs (OpenAlex, Semantic Scholar)
        - Local files (PDF, DOCX, PPTX, images)
        """
        sources: List[Source] = []
        # Placeholder — will be implemented in Phase 3
        return sources

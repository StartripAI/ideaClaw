"""Source screener — relevance and quality filtering.

TODO: Port screening logic from OpenRevise check_revise_sources.py
"""

from __future__ import annotations

from typing import Any, Dict, List

from ideaclaw.source.collector import Source


class SourceScreener:
    """Screens collected sources for relevance and quality."""

    def __init__(self, config: Dict[str, Any]):
        self.quality_threshold = config.get("quality_threshold", 4.0)

    def screen(self, sources: List[Source]) -> List[Source]:
        """Filter sources by relevance and quality threshold.

        TODO: Implement LLM-based screening.
        """
        return [s for s in sources if s.quality_score >= self.quality_threshold]

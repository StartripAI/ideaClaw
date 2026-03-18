"""Source screener — relevance and quality filtering.

Filters collected sources by:
1. Relevance scoring (TF-IDF-like keyword overlap)
2. Recency weighting
3. Citation count thresholds
4. Source tier from registry
5. Duplicate removal
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from ideaclaw.source.collector import SourceResult

# Domain-to-tier mapping for quick lookup (expanded from SourceRegistry)
SOURCE_TIERS = {
    "arxiv.org": {"tier": "preprint"},
    "pubmed.ncbi.nlm.nih.gov": {"tier": "peer_reviewed"},
    "doi.org": {"tier": "academic"},
    "semanticscholar.org": {"tier": "academic"},
    "openalex.org": {"tier": "academic"},
    "nature.com": {"tier": "peer_reviewed"},
    "sciencedirect.com": {"tier": "peer_reviewed"},
    "ieee.org": {"tier": "peer_reviewed"},
    "acm.org": {"tier": "peer_reviewed"},
    "springer.com": {"tier": "peer_reviewed"},
    "wiley.com": {"tier": "peer_reviewed"},
    "gov": {"tier": "peer_reviewed"},
    "edu": {"tier": "academic"},
    "wikipedia.org": {"tier": "web"},
    "medium.com": {"tier": "web"},
    "reddit.com": {"tier": "web"},
}


@dataclass
class ScreenedSource:
    """A source that has passed screening with scores."""
    source: SourceResult
    relevance_score: float
    tier: str
    passed: bool
    reason: str = ""


def _tokenize(text: str) -> Set[str]:
    """Simple word tokenization for relevance scoring."""
    return set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", text.lower()))


def _compute_relevance(source: SourceResult, query_tokens: Set[str]) -> float:
    """TF-IDF-like relevance score: fraction of query tokens found in title+abstract."""
    if not query_tokens:
        return 0.0
    source_text = f"{source.title} {source.abstract}"
    source_tokens = _tokenize(source_text)
    if not source_tokens:
        return 0.0
    overlap = query_tokens & source_tokens
    # Weighted: title matches count 2x
    title_tokens = _tokenize(source.title)
    title_overlap = query_tokens & title_tokens
    score = (len(overlap) + len(title_overlap)) / (len(query_tokens) * 2)
    return min(score, 1.0)


def _recency_weight(year: Optional[int], current_year: int = 2026) -> float:
    """Weight source by recency: 1.0 for current year, decaying for older."""
    if year is None:
        return 0.5  # Unknown year gets neutral weight
    age = current_year - year
    if age <= 0:
        return 1.0
    if age <= 2:
        return 0.95
    if age <= 5:
        return 0.85
    if age <= 10:
        return 0.70
    return 0.50


def _citation_weight(count: int) -> float:
    """Weight source by citation count."""
    if count >= 100:
        return 1.0
    if count >= 50:
        return 0.9
    if count >= 10:
        return 0.8
    if count >= 1:
        return 0.7
    return 0.5  # No citations yet (new paper)


def _get_source_tier(source: SourceResult) -> str:
    """Look up source tier from registry."""
    # Check by domain in URL
    for domain, tier_info in SOURCE_TIERS.items():
        if domain in source.url.lower():
            return tier_info.get("tier", "unknown")
    # Default by API
    api_tiers = {
        "arxiv": "preprint",
        "semantic_scholar": "academic",
        "pubmed": "peer_reviewed",
        "openalex": "academic",
        "web": "web",
    }
    return api_tiers.get(source.source_api, "unknown")


def screen_sources(
    sources: List[SourceResult],
    query: str,
    min_relevance: float = 0.15,
    min_tier: str = "web",
    max_results: int = 30,
    config: Optional[Dict[str, Any]] = None,
) -> List[ScreenedSource]:
    """Screen and rank collected sources.

    Args:
        sources: Raw sources from collector.
        query: Original search query for relevance scoring.
        min_relevance: Minimum relevance score to pass (0.0 - 1.0).
        min_tier: Minimum source tier to accept.
        max_results: Maximum number of screened sources to return.
        config: Optional configuration dict.

    Returns:
        Sorted list of ScreenedSource, highest relevance first.
    """
    TIER_RANK = {"peer_reviewed": 4, "academic": 3, "preprint": 2, "web": 1, "unknown": 0}
    min_tier_rank = TIER_RANK.get(min_tier, 0)

    query_tokens = _tokenize(query)
    results: List[ScreenedSource] = []

    for source in sources:
        # 1. Relevance
        relevance = _compute_relevance(source, query_tokens)

        # 2. Recency
        recency = _recency_weight(source.year)

        # 3. Citation
        citation = _citation_weight(source.citation_count)

        # 4. Tier
        tier = _get_source_tier(source)
        tier_rank = TIER_RANK.get(tier, 0)

        # Composite score: 40% relevance, 20% recency, 20% citations, 20% tier
        composite = (
            relevance * 0.40
            + recency * 0.20
            + citation * 0.20
            + (tier_rank / 4.0) * 0.20
        )

        # Pass/fail checks
        passed = True
        reason = ""
        if relevance < min_relevance:
            passed = False
            reason = f"low_relevance ({relevance:.2f} < {min_relevance})"
        elif tier_rank < min_tier_rank:
            passed = False
            reason = f"tier_too_low ({tier} < {min_tier})"

        results.append(ScreenedSource(
            source=source,
            relevance_score=composite,
            tier=tier,
            passed=passed,
            reason=reason,
        ))

    # Sort by composite relevance (desc)
    results.sort(key=lambda r: -r.relevance_score)

    # Return passed sources first, up to max_results
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    return (passed + failed)[:max_results]

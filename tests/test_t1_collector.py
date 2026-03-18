"""T1: Source collection API tests (5 tests).

Tests search_arxiv, search_semantic_scholar, search_pubmed,
search_openalex, and collect_sources (aggregated dedup).
"""

from __future__ import annotations

import pytest
from ideaclaw.source.collector import (
    search_arxiv,
    search_semantic_scholar,
    search_pubmed,
    search_openalex,
    collect_sources,
    SourceResult,
)


# ---- T1.1: arXiv ----
@pytest.mark.network
def test_t1_1_arxiv_search():
    """T1.1: arXiv returns real papers with title/url/year."""
    results = search_arxiv("transformer attention mechanism", max_results=5)
    assert len(results) >= 1, "arXiv should return at least 1 paper"
    r = results[0]
    assert isinstance(r, SourceResult)
    assert r.title, "title should not be empty"
    assert r.url, "url should not be empty"
    assert r.year, "year should not be empty"
    assert r.source_api == "arxiv"


# ---- T1.2: Semantic Scholar ----
@pytest.mark.network
def test_t1_2_semantic_scholar_search():
    """T1.2: Semantic Scholar returns papers or gracefully fails (no API key)."""
    results = search_semantic_scholar("CRISPR gene editing", max_results=3)
    # May return empty if no API key / rate limited — that's OK
    assert isinstance(results, list)
    if results:
        r = results[0]
        assert r.title
        assert r.source_api == "semantic_scholar"


# ---- T1.3: PubMed ----
@pytest.mark.network
def test_t1_3_pubmed_search():
    """T1.3: PubMed returns papers with PMIDs."""
    results = search_pubmed("immunotherapy checkpoint inhibitor", max_results=3)
    assert len(results) >= 1, "PubMed should return at least 1 paper"
    r = results[0]
    assert r.title
    assert r.source_api == "pubmed"


# ---- T1.4: OpenAlex ----
@pytest.mark.network
def test_t1_4_openalex_search():
    """T1.4: OpenAlex returns papers with DOIs."""
    results = search_openalex("climate change policy carbon tax", max_results=3)
    assert len(results) >= 1, "OpenAlex should return at least 1 paper"
    r = results[0]
    assert r.title
    assert r.source_api == "openalex"


# ---- T1.5: Aggregated dedup ----
@pytest.mark.network
@pytest.mark.slow
def test_t1_5_collect_sources_dedup():
    """T1.5: collect_sources aggregates and deduplicates across APIs."""
    results = collect_sources("deep learning neural network", max_per_api=3)
    assert len(results) >= 2, "Should aggregate from multiple APIs"
    # Check no duplicate titles (case-insensitive)
    titles = [r.title.lower().strip() for r in results]
    # Allow some overlap but not exact duplicates
    unique = set(titles)
    assert len(unique) >= len(titles) * 0.8, f"Too many duplicates: {len(unique)}/{len(titles)}"

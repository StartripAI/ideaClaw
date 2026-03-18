"""T2: Source screening tests (3 tests).

Tests composite scoring, tier classification, and low-relevance filtering.
"""

from __future__ import annotations

import pytest
from ideaclaw.source.collector import SourceResult
from ideaclaw.source.screener import screen_sources


def _make_source(title: str, url: str, year: int = 2024, citations: int = 10) -> SourceResult:
    return SourceResult(
        title=title,
        url=url,
        year=year,  # Must be int, not str
        source_api="test",
        authors=[],
        abstract=title,
        doi="",
        citation_count=citations,
    )


# ---- T2.1: Relevance ranking ----
def test_t2_1_relevance_ranking():
    """T2.1: Top result should have relevance > 0.3 for matching query."""
    sources = [
        _make_source("Transformer Models for NLP", "https://arxiv.org/abs/1", citations=100),
        _make_source("Cooking Italian Pasta Recipes", "https://example.com/pasta", citations=5),
        _make_source("Attention Mechanisms in Deep Learning", "https://arxiv.org/abs/2", citations=50),
    ]
    screened = screen_sources(sources, "transformer attention deep learning")
    assert len(screened) >= 1
    top = screened[0]
    assert top.relevance_score > 0.3, f"Top relevance too low: {top.relevance_score}"


# ---- T2.2: Tier classification ----
def test_t2_2_tier_classification():
    """T2.2: arXiv sources should be classified as preprint tier."""
    sources = [
        _make_source("Test Paper", "https://arxiv.org/abs/2024.12345"),
    ]
    screened = screen_sources(sources, "test paper")
    assert len(screened) == 1
    assert screened[0].tier == "preprint", f"Expected preprint, got {screened[0].tier}"


# ---- T2.3: Low-relevance filtering ----
def test_t2_3_low_relevance_filter():
    """T2.3: Completely irrelevant papers should have low relevance."""
    sources = [
        _make_source("Quantum Computing Algorithms", "https://example.com/quantum"),
    ]
    screened = screen_sources(sources, "italian cooking pasta recipe")
    assert len(screened) >= 1
    assert screened[0].relevance_score < 0.5, f"Irrelevant paper scored too high: {screened[0].relevance_score}"

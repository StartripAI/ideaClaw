"""T5: Citation verification tests (4 tests).

Tests DOI verification, arXiv verification, fake DOI rejection,
and citation summary with mixed results.
"""

from __future__ import annotations

import pytest
from ideaclaw.evidence.citation_verify import (
    verify_doi,
    verify_arxiv,
    verify_citations,
    citation_summary,
    _extract_identifiers,
    CitationCheck,
)


# ---- T5.1: DOI verification ----
@pytest.mark.network
def test_t5_1_doi_verification():
    """T5.1: Known DOI should resolve via CrossRef."""
    result = verify_doi("10.1038/nature12373")
    assert result.verified, f"Known DOI should verify: {result.detail}"
    assert result.resolved_title, "Should have a resolved title"
    assert result.identifier_type == "doi"


# ---- T5.2: arXiv verification ----
@pytest.mark.network
def test_t5_2_arxiv_verification():
    """T5.2: Known arXiv ID should resolve via API."""
    result = verify_arxiv("1706.03762")
    # May be flaky due to arXiv API instability (502s)
    if result.verified:
        assert "attention" in result.resolved_title.lower(), \
            f"Should be 'Attention Is All You Need', got: {result.resolved_title}"
    else:
        # Accept graceful failure (API may be down)
        assert "failed" in result.detail.lower() or "not_found" in result.detail


# ---- T5.3: Fake DOI ----
@pytest.mark.network
def test_t5_3_fake_doi_rejected():
    """T5.3: Fake DOI should not verify."""
    result = verify_doi("10.9999/this.doi.does.not.exist.99999")
    assert not result.verified, "Fake DOI should not verify"


# ---- T5.4: Citation summary ----
def test_t5_4_citation_summary():
    """T5.4: Citation summary should calculate correct verdict."""
    results = [
        CitationCheck("a", "a", "doi", verified=True, detail="ok"),
        CitationCheck("b", "b", "arxiv", verified=True, detail="ok"),
        CitationCheck("c", "c", "doi", verified=True, detail="ok"),
        CitationCheck("d", "d", "url", verified=False, detail="unreachable"),
    ]
    summary = citation_summary(results)
    assert summary["total"] == 4
    assert summary["verified"] == 3
    assert summary["failed"] == 1
    assert summary["verification_rate"] == 0.75
    assert summary["verdict"] == "PASS", f"75% should be PASS, got {summary['verdict']}"


# ---- Bonus: identifier extraction ----
def test_t5_bonus_identifier_extraction():
    """Bonus: Extract DOI, arXiv, PMID, URL from mixed text."""
    text = "See doi:10.1038/nature12373, arXiv:1706.03762, PMID:12345678, and https://example.com"
    ids = _extract_identifiers(text)
    types = sorted(set(t for _, t in ids))
    assert "doi" in types, f"Should extract DOI, got types: {types}"
    assert "arxiv" in types
    assert "pmid" in types
    assert "url" in types
    assert len(ids) == 4, f"Should extract 4 identifiers, got {len(ids)}"

"""T5: Citation verification tests.

Tests BibTeX parsing, title similarity, DOI/arXiv verification,
verification report generation, and hallucination annotation.
"""

from __future__ import annotations

import pytest
from ideaclaw.evidence.citation_verify import (
    VerifyStatus,
    CitationResult,
    VerificationReport,
    parse_bibtex_entries,
    title_similarity,
    verify_by_doi,
    verify_by_arxiv_id,
    verify_citations,
    filter_verified_bibtex,
    annotate_paper_hallucinations,
)


# ---- T5.1: DOI verification ----
@pytest.mark.network
def test_t5_1_doi_verification():
    """T5.1: Known DOI should resolve via CrossRef."""
    result = verify_by_doi("10.1038/nature12373", "Genomic evidence...")
    assert result is not None, "Should get a result for valid DOI"
    assert result.status in (VerifyStatus.VERIFIED, VerifyStatus.SUSPICIOUS), \
        f"Known DOI should verify or be suspicious, got {result.status}"


# ---- T5.2: arXiv verification ----
@pytest.mark.network
def test_t5_2_arxiv_verification():
    """T5.2: Known arXiv ID should resolve via API."""
    result = verify_by_arxiv_id("1706.03762", "Attention Is All You Need")
    if result is not None:
        assert result.status in (VerifyStatus.VERIFIED, VerifyStatus.SUSPICIOUS)
    # None means network failure — acceptable in CI


# ---- T5.3: Fake DOI ----
@pytest.mark.network
def test_t5_3_fake_doi_rejected():
    """T5.3: Fake DOI should not verify."""
    result = verify_by_doi("10.9999/this.doi.does.not.exist.99999", "Nonexistent Paper")
    assert result is not None
    assert result.status == VerifyStatus.HALLUCINATED, f"Got {result.status}"


# ---- T5.4: Citation summary ----
def test_t5_4_citation_summary():
    """T5.4: VerificationReport should calculate correct integrity score."""
    report = VerificationReport(
        total=4, verified=3, hallucinated=1,
        results=[
            CitationResult("a", "title_a", VerifyStatus.VERIFIED, 0.9, "doi"),
            CitationResult("b", "title_b", VerifyStatus.VERIFIED, 0.85, "arxiv_id"),
            CitationResult("c", "title_c", VerifyStatus.VERIFIED, 0.95, "openalex"),
            CitationResult("d", "title_d", VerifyStatus.HALLUCINATED, 0.7, "title_search"),
        ],
    )
    assert report.integrity_score == 0.75
    md = report.to_markdown()
    assert "✅" in md
    assert "❌" in md


# ---- T5.5: BibTeX parsing ----
def test_t5_5_bibtex_parsing():
    """T5.5: Parse BibTeX entries correctly."""
    bib = """@article{vaswani2017,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam},
  year = {2017},
  eprint = {1706.03762},
}

@inproceedings{devlin2019,
  title = {BERT: Pre-training of Deep Bidirectional Transformers},
  author = {Devlin, Jacob},
  year = {2019},
  doi = {10.18653/v1/N19-1423},
}"""
    entries = parse_bibtex_entries(bib)
    assert len(entries) == 2
    assert entries[0]["key"] == "vaswani2017"
    assert entries[0]["eprint"] == "1706.03762"
    assert entries[1]["doi"] == "10.18653/v1/N19-1423"


# ---- T5.6: Title similarity ----
def test_t5_6_title_similarity():
    """T5.6: Title similarity should work correctly."""
    assert title_similarity("Attention Is All You Need", "attention is all you need") == 1.0
    assert title_similarity("Attention Is All You Need", "Some Completely Different Paper") < 0.5
    assert title_similarity("", "anything") == 0.0


# ---- T5.7: Annotate hallucinations ----
def test_t5_7_annotate_hallucinations():
    """T5.7: Hallucinated citations should be removed from text."""
    report = VerificationReport(total=2, results=[
        CitationResult("real2023", "", VerifyStatus.VERIFIED, 1.0, ""),
        CitationResult("fake2024", "", VerifyStatus.HALLUCINATED, 1.0, ""),
    ])

    # LaTeX format
    text_latex = r"As shown by \cite{real2023, fake2024}, it works."
    cleaned = annotate_paper_hallucinations(text_latex, report)
    assert "fake2024" not in cleaned
    assert "real2023" in cleaned

    # Markdown format
    text_md = "As shown by [real2023, fake2024], it works."
    cleaned_md = annotate_paper_hallucinations(text_md, report)
    assert "fake2024" not in cleaned_md
    assert "real2023" in cleaned_md


# ---- T5.8: Filter verified BibTeX ----
def test_t5_8_filter_bibtex():
    """T5.8: filter_verified_bibtex should keep only verified entries."""
    bib = """@article{real2023,
  title = {Real Paper},
}

@article{fake2024,
  title = {Fake Paper},
}"""
    report = VerificationReport(total=2, results=[
        CitationResult("real2023", "Real Paper", VerifyStatus.VERIFIED, 1.0, "doi"),
        CitationResult("fake2024", "Fake Paper", VerifyStatus.HALLUCINATED, 0.7, "title_search"),
    ])
    filtered = filter_verified_bibtex(bib, report, include_suspicious=False)
    assert "real2023" in filtered
    assert "fake2024" not in filtered

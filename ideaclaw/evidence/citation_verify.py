"""Citation verification engine — detect hallucinated references.

Ported from ARC's literature/verify.py with enhancements:
  - 4-layer verification strategy (optimized order)
  - SHA-256 disk cache for verified results
  - Adaptive rate limiting per API
  - Global timeout (5 min default)
  - BibTeX filtering + hallucination annotation

Verification layers (optimized order for rate limits):
  L1: DOI → CrossRef API (fast, 50 req/s polite pool)
       Falls back to DataCite for arXiv DOIs
  L2: Title → OpenAlex API (10K calls/day)
  L3: arXiv ID → arXiv API (conservative, 1/3s)
  L4: Title → Semantic Scholar + arXiv title search (last resort)

Classifications:
  VERIFIED:      API confirms + title similarity ≥ 0.80
  SUSPICIOUS:    Found but metadata diverges (0.50 ≤ sim < 0.80)
  HALLUCINATED:  Not found via any API or sim < 0.50
  SKIPPED:       Cannot verify (no title, or all APIs unreachable)

All network I/O uses stdlib urllib — zero extra pip dependencies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class VerifyStatus(str, Enum):
    """Verification outcome for a single citation."""
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    HALLUCINATED = "hallucinated"
    SKIPPED = "skipped"


@dataclass
class CitationResult:
    """Verification result for one BibTeX entry."""
    cite_key: str
    title: str
    status: VerifyStatus
    confidence: float          # 0.0–1.0
    method: str                # "arxiv_id" | "doi" | "openalex" | "title_search" | "skipped"
    details: str = ""
    matched_title: str = ""    # Title of the matched paper (if found)
    matched_authors: List[str] = field(default_factory=list)
    matched_year: Optional[int] = None
    matched_source: str = ""
    relevance_score: Optional[float] = None

    def to_dict(self) -> dict:
        d = {
            "cite_key": self.cite_key,
            "title": self.title,
            "status": self.status.value,
            "confidence": round(self.confidence, 3),
            "method": self.method,
            "details": self.details,
        }
        if self.matched_title:
            d["matched_title"] = self.matched_title
        if self.matched_authors:
            d["matched_authors"] = self.matched_authors
        if self.matched_year:
            d["matched_year"] = self.matched_year
        if self.relevance_score is not None:
            d["relevance_score"] = round(self.relevance_score, 2)
        return d


@dataclass
class VerificationReport:
    """Aggregate report for all citations in a paper."""
    total: int = 0
    verified: int = 0
    suspicious: int = 0
    hallucinated: int = 0
    skipped: int = 0
    results: List[CitationResult] = field(default_factory=list)

    @property
    def integrity_score(self) -> float:
        """Fraction of verifiable citations that are verified (0.0–1.0)."""
        verifiable = self.total - self.skipped
        if verifiable <= 0:
            return 1.0
        return round(self.verified / verifiable, 3)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": self.total,
                "verified": self.verified,
                "suspicious": self.suspicious,
                "hallucinated": self.hallucinated,
                "skipped": self.skipped,
                "integrity_score": self.integrity_score,
            },
            "results": [r.to_dict() for r in self.results],
        }

    def to_markdown(self) -> str:
        """Generate a markdown summary report."""
        lines = [
            "# Citation Verification Report",
            "",
            f"**Total**: {self.total} | "
            f"✅ Verified: {self.verified} | "
            f"⚠️ Suspicious: {self.suspicious} | "
            f"❌ Hallucinated: {self.hallucinated} | "
            f"⏭️ Skipped: {self.skipped}",
            f"**Integrity Score**: {self.integrity_score:.1%}",
            "",
            "| # | Key | Status | Confidence | Method | Details |",
            "|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(self.results, 1):
            icon = {"verified": "✅", "suspicious": "⚠️",
                    "hallucinated": "❌", "skipped": "⏭️"}.get(r.status.value, "?")
            lines.append(
                f"| {i} | `{r.cite_key}` | {icon} {r.status.value} | "
                f"{r.confidence:.2f} | {r.method} | {r.details[:60]} |"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# BibTeX parser
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(
    r"@(\w+)\s*\{\s*([^,\s]+)\s*,\s*(.*?)\n\}",
    re.DOTALL,
)

_FIELD_RE = re.compile(r"(\w+)\s*=\s*\{([^}]*)\}", re.DOTALL)


def parse_bibtex_entries(bib_text: str) -> List[dict]:
    """Parse BibTeX text into a list of field dicts.

    Each dict has at least 'key' and 'type', plus parsed fields
    (title, author, year, doi, eprint, url, ...).
    """
    entries = []
    for m in _ENTRY_RE.finditer(bib_text):
        entry = {
            "type": m.group(1).lower(),
            "key": m.group(2).strip(),
        }
        body = m.group(3)
        for fm in _FIELD_RE.finditer(body):
            entry[fm.group(1).lower()] = fm.group(2).strip()
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Title similarity
# ---------------------------------------------------------------------------

def title_similarity(a: str, b: str) -> float:
    """Word-overlap Jaccard similarity between two titles (0.0–1.0).

    Uses max(len) as denominator so short titles don't inflate score.
    """
    def _words(t: str) -> set:
        return set(re.sub(r"[^a-z0-9\s]", "", t.lower()).split()) - {""}

    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


# ---------------------------------------------------------------------------
# L1: arXiv ID lookup
# ---------------------------------------------------------------------------

_ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
_ARXIV_TIMEOUT = 20


def verify_by_arxiv_id(arxiv_id: str, expected_title: str) -> Optional[CitationResult]:
    """Look up a paper by arXiv ID and compare titles.

    Returns None on network failure (caller falls through to next layer).
    """
    params = urllib.parse.urlencode({"id_list": arxiv_id, "max_results": "1"})
    url = f"{_ARXIV_API}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IdeaClaw/1.0"})
        with urllib.request.urlopen(req, timeout=_ARXIV_TIMEOUT) as resp:
            data = resp.read().decode("utf-8")
    except Exception as exc:
        logger.debug("arXiv ID verification failed for %s: %s", arxiv_id, exc)
        return None

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    entries = root.findall("atom:entry", _ARXIV_NS)
    if not entries:
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.HALLUCINATED, confidence=0.9,
            method="arxiv_id",
            details=f"arXiv ID {arxiv_id} not found",
        )

    entry = entries[0]
    found_title_el = entry.find("atom:title", _ARXIV_NS)
    found_title = (found_title_el.text or "").strip() if found_title_el is not None else ""
    found_title = re.sub(r"\s+", " ", found_title)

    # Check for arXiv error responses
    entry_id = entry.findtext("atom:id", "", _ARXIV_NS)
    if "api/errors" in entry_id or not found_title or found_title.lower() == "error":
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.HALLUCINATED, confidence=0.9,
            method="arxiv_id",
            details=f"arXiv ID {arxiv_id} returned error",
        )

    sim = title_similarity(expected_title, found_title)
    if sim >= 0.80:
        status = VerifyStatus.VERIFIED
    elif sim >= 0.50:
        status = VerifyStatus.SUSPICIOUS
    else:
        status = VerifyStatus.SUSPICIOUS

    return CitationResult(
        cite_key="", title=expected_title,
        status=status, confidence=sim,
        method="arxiv_id",
        details=f"arXiv: '{found_title}' (sim={sim:.2f})",
        matched_title=found_title,
    )


# ---------------------------------------------------------------------------
# L2: DOI verification via CrossRef + DataCite fallback
# ---------------------------------------------------------------------------

_CROSSREF_API = "https://api.crossref.org/works"
_CROSSREF_TIMEOUT = 20
_DATACITE_API = "https://api.datacite.org/dois"
_DATACITE_TIMEOUT = 15


def _verify_doi_datacite(doi: str, expected_title: str) -> Optional[CitationResult]:
    """Fallback DOI verification via DataCite (for arXiv DOIs)."""
    encoded_doi = urllib.parse.quote(doi, safe="")
    url = f"{_DATACITE_API}/{encoded_doi}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "IdeaClaw/1.0", "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=_DATACITE_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return CitationResult(
                cite_key="", title=expected_title,
                status=VerifyStatus.HALLUCINATED, confidence=0.9,
                method="doi",
                details=f"DOI {doi} not found via CrossRef or DataCite",
            )
        return None
    except Exception:
        return None

    attrs = body.get("data", {}).get("attributes", {})
    dc_titles = attrs.get("titles", [])
    found_title = dc_titles[0].get("title", "") if dc_titles else ""

    if not found_title:
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.VERIFIED, confidence=0.85,
            method="doi",
            details=f"DOI {doi} resolves via DataCite (no title to compare)",
        )

    sim = title_similarity(expected_title, found_title)
    status = VerifyStatus.VERIFIED if sim >= 0.80 else VerifyStatus.SUSPICIOUS
    return CitationResult(
        cite_key="", title=expected_title,
        status=status, confidence=sim,
        method="doi",
        details=f"DataCite: '{found_title}' (sim={sim:.2f})",
        matched_title=found_title,
    )


def verify_by_doi(doi: str, expected_title: str) -> Optional[CitationResult]:
    """Verify DOI via CrossRef, with DataCite fallback for arXiv DOIs."""
    encoded_doi = urllib.parse.quote(doi, safe="")
    url = f"{_CROSSREF_API}/{encoded_doi}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "IdeaClaw/1.0 (mailto:ideaclaw@users.noreply.github.com)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=_CROSSREF_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            if doi.startswith("10.48550/") or doi.startswith("10.5281/"):
                dc = _verify_doi_datacite(doi, expected_title)
                if dc is not None:
                    return dc
            return CitationResult(
                cite_key="", title=expected_title,
                status=VerifyStatus.HALLUCINATED, confidence=0.9,
                method="doi", details=f"DOI {doi} not found (404)",
            )
        return None
    except Exception:
        return None

    message = body.get("message", {})
    titles = message.get("title", [])
    found_title = titles[0] if titles else ""

    if not found_title:
        return CitationResult(
            cite_key="", title=expected_title,
            status=VerifyStatus.VERIFIED, confidence=0.85,
            method="doi",
            details=f"DOI {doi} resolves via CrossRef (no title to compare)",
        )

    sim = title_similarity(expected_title, found_title)
    status = VerifyStatus.VERIFIED if sim >= 0.80 else VerifyStatus.SUSPICIOUS
    return CitationResult(
        cite_key="", title=expected_title,
        status=status, confidence=sim,
        method="doi",
        details=f"CrossRef: '{found_title}' (sim={sim:.2f})",
        matched_title=found_title,
    )


# ---------------------------------------------------------------------------
# L3: OpenAlex title search (high rate limits)
# ---------------------------------------------------------------------------

_OPENALEX_API = "https://api.openalex.org/works"
_OPENALEX_TIMEOUT = 15
_OPENALEX_EMAIL = "ideaclaw@users.noreply.github.com"


def verify_by_openalex(title: str) -> Optional[CitationResult]:
    """Verify via OpenAlex API (10K+ calls/day)."""
    params = urllib.parse.urlencode({
        "filter": f"title.search:{title}",
        "per_page": "5",
        "mailto": _OPENALEX_EMAIL,
    })
    url = f"{_OPENALEX_API}?{params}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": f"IdeaClaw/1.0 (mailto:{_OPENALEX_EMAIL})",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=_OPENALEX_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    results = body.get("results", [])
    if not results:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.HALLUCINATED, confidence=0.7,
            method="openalex", details="No results via OpenAlex",
        )

    best_sim, best_title = 0.0, ""
    for r in results:
        ft = r.get("title", "")
        if ft:
            sim = title_similarity(title, ft)
            if sim > best_sim:
                best_sim, best_title = sim, ft

    if best_sim >= 0.80:
        status = VerifyStatus.VERIFIED
    elif best_sim >= 0.50:
        status = VerifyStatus.SUSPICIOUS
    else:
        status = VerifyStatus.HALLUCINATED

    return CitationResult(
        cite_key="", title=title,
        status=status, confidence=best_sim if best_sim >= 0.50 else 0.7,
        method="openalex",
        details=f"OpenAlex: '{best_title}' (sim={best_sim:.2f})" if best_title else "No close match",
        matched_title=best_title,
    )


# ---------------------------------------------------------------------------
# L4: Title search via IdeaClaw source module
# ---------------------------------------------------------------------------

def verify_by_title_search(title: str) -> Optional[CitationResult]:
    """Search by title using IdeaClaw's source module. Last resort."""
    try:
        from ideaclaw.source.search import search_sources
        results = search_sources(title, limit=5)
    except Exception:
        return None

    if not results:
        return CitationResult(
            cite_key="", title=title,
            status=VerifyStatus.HALLUCINATED, confidence=0.7,
            method="title_search",
            details="No results via Semantic Scholar + arXiv",
        )

    best_sim, best_paper = 0.0, None
    for paper in results:
        paper_title = paper.get("title", "") if isinstance(paper, dict) else getattr(paper, "title", "")
        if paper_title:
            sim = title_similarity(title, paper_title)
            if sim > best_sim:
                best_sim, best_paper = sim, paper

    bp_title = ""
    if best_paper:
        bp_title = best_paper.get("title", "") if isinstance(best_paper, dict) else getattr(best_paper, "title", "")

    if best_sim >= 0.80:
        status = VerifyStatus.VERIFIED
    elif best_sim >= 0.50:
        status = VerifyStatus.SUSPICIOUS
    else:
        status = VerifyStatus.HALLUCINATED

    return CitationResult(
        cite_key="", title=title,
        status=status, confidence=best_sim if best_sim >= 0.50 else (1.0 - best_sim),
        method="title_search",
        details=f"Search: '{bp_title}' (sim={best_sim:.2f})" if bp_title else "No match",
        matched_title=bp_title,
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_DIR = Path.home() / ".cache" / "ideaclaw" / "citation_verify"


def _cache_key(title: str) -> str:
    return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]


def _read_cache(title: str) -> Optional[CitationResult]:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{_cache_key(title)}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return CitationResult(
                cite_key=data.get("cite_key", ""),
                title=data.get("title", title),
                status=VerifyStatus(data["status"]),
                confidence=data["confidence"],
                method=data["method"],
                details=data.get("details", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None
    return None


def _write_cache(title: str, result: CitationResult) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{_cache_key(title)}.json"
    cache_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry: verify_citations
# ---------------------------------------------------------------------------

def verify_citations(
    bib_text: str,
    *,
    inter_verify_delay: float = 1.5,
    global_timeout_sec: float = 300.0,
) -> VerificationReport:
    """Verify all BibTeX entries against real academic APIs.

    4-layer verification (optimized order for rate limits):
      L1: DOI → CrossRef (fast, high limit)
      L2: Title → OpenAlex (10K/day)
      L3: arXiv ID → arXiv API (conservative)
      L4: Title → S2 + arXiv search (last resort)

    Parameters
    ----------
    bib_text : str
        Raw BibTeX string.
    inter_verify_delay : float
        Base delay between API calls (seconds).
    global_timeout_sec : float
        Total timeout for all verifications (default 5 min).
    """
    entries = parse_bibtex_entries(bib_text)
    report = VerificationReport(total=len(entries))

    # Adaptive delays per API
    DELAY_CROSSREF = 0.3
    DELAY_OPENALEX = 0.2
    DELAY_ARXIV = inter_verify_delay
    api_call_count = 0

    verify_start = time.monotonic()

    for i, entry in enumerate(entries):
        # Global timeout — mark remaining as SKIPPED
        if time.monotonic() - verify_start > global_timeout_sec:
            logger.warning("Verification timeout (%.0fs). Skipping remaining %d/%d.",
                           global_timeout_sec, len(entries) - i, len(entries))
            for remaining in entries[i:]:
                rkey = remaining.get("key", f"unknown_{i}")
                report.results.append(CitationResult(
                    cite_key=rkey, title=remaining.get("title", ""),
                    status=VerifyStatus.SKIPPED, confidence=0.0,
                    method="skipped", details="Verification timeout exceeded",
                ))
                report.skipped += 1
            break

        key = entry.get("key", f"unknown_{i}")
        title = entry.get("title", "")
        arxiv_id = entry.get("eprint", "")
        doi = entry.get("doi", "")

        # Skip entries with no title
        if not title:
            report.results.append(CitationResult(
                cite_key=key, title="",
                status=VerifyStatus.SKIPPED, confidence=0.0,
                method="skipped", details="No title in BibTeX entry",
            ))
            report.skipped += 1
            continue

        # Check cache first
        cached = _read_cache(title)
        if cached is not None:
            cached = CitationResult(
                cite_key=key, title=cached.title, status=cached.status,
                confidence=cached.confidence, method=cached.method,
                details=cached.details,
            )
            report.results.append(cached)
            if cached.status == VerifyStatus.VERIFIED:
                report.verified += 1
            elif cached.status == VerifyStatus.SUSPICIOUS:
                report.suspicious += 1
            elif cached.status == VerifyStatus.HALLUCINATED:
                report.hallucinated += 1
            else:
                report.skipped += 1
            continue

        result: Optional[CitationResult] = None

        # L1: DOI → CrossRef (fast, generous limits)
        if result is None and doi:
            if api_call_count > 0:
                time.sleep(DELAY_CROSSREF)
            result = verify_by_doi(doi, title)
            api_call_count += 1

        # L2: OpenAlex title search (high rate limits)
        if result is None:
            if api_call_count > 0:
                time.sleep(DELAY_OPENALEX)
            result = verify_by_openalex(title)
            api_call_count += 1

        # L3: arXiv ID (if DOI and OpenAlex both failed)
        if result is None and arxiv_id:
            if api_call_count > 0:
                time.sleep(DELAY_ARXIV)
            result = verify_by_arxiv_id(arxiv_id, title)
            api_call_count += 1

        # L4: Title search (last resort)
        if result is None:
            result = verify_by_title_search(title)
            api_call_count += 1

        # Fallback: all layers failed
        if result is None:
            result = CitationResult(
                cite_key=key, title=title,
                status=VerifyStatus.SKIPPED, confidence=0.0,
                method="skipped",
                details="All verification methods failed (network?)",
            )

        # Set cite_key from parsed entry
        result = CitationResult(
            cite_key=key, title=result.title, status=result.status,
            confidence=result.confidence, method=result.method,
            details=result.details, matched_title=result.matched_title,
        )

        # Cache (skip SKIPPED — network failures shouldn't persist)
        if result.status != VerifyStatus.SKIPPED:
            _write_cache(title, result)

        if result.status == VerifyStatus.VERIFIED:
            report.verified += 1
        elif result.status == VerifyStatus.SUSPICIOUS:
            report.suspicious += 1
        elif result.status == VerifyStatus.HALLUCINATED:
            report.hallucinated += 1
        else:
            report.skipped += 1

        report.results.append(result)

    return report


# ---------------------------------------------------------------------------
# Utilities: filter & annotate
# ---------------------------------------------------------------------------

def filter_verified_bibtex(
    bib_text: str,
    report: VerificationReport,
    *,
    include_suspicious: bool = True,
) -> str:
    """Return BibTeX with only verified (+ optionally suspicious) entries."""
    keep_keys = set()
    for r in report.results:
        if r.status == VerifyStatus.VERIFIED:
            keep_keys.add(r.cite_key)
        elif r.status == VerifyStatus.SUSPICIOUS and include_suspicious:
            keep_keys.add(r.cite_key)
        elif r.status == VerifyStatus.SKIPPED:
            keep_keys.add(r.cite_key)

    kept = []
    for m in _ENTRY_RE.finditer(bib_text):
        if m.group(2).strip() in keep_keys:
            kept.append(m.group(0))

    return "\n\n".join(kept) + "\n" if kept else ""


def annotate_paper_hallucinations(
    paper_text: str,
    report: VerificationReport,
) -> str:
    """Remove hallucinated citations from paper text.

    Handles both \\cite{key} (LaTeX) and [key] (Markdown) formats.
    """
    hallucinated_keys = {r.cite_key for r in report.results
                         if r.status == VerifyStatus.HALLUCINATED}
    if not hallucinated_keys:
        return paper_text

    result = paper_text

    # Handle \cite{key1, key2} — remove only hallucinated keys
    def _replace_latex(m: re.Match) -> str:
        keys = [k.strip() for k in m.group(1).split(",")]
        kept = [k for k in keys if k not in hallucinated_keys]
        if not kept:
            return ""
        return "\\cite{" + ", ".join(kept) + "}"

    result = re.sub(r"\\cite\{([^}]+)\}", _replace_latex, result)

    # Handle [key1, key2] markdown citations
    _CITE_KEY_PAT = r"[a-zA-Z]+\d{4}[a-zA-Z]*"

    def _replace_markdown(m: re.Match) -> str:
        keys = [k.strip() for k in re.split(r"[,;]\s*", m.group(1))]
        kept = [k for k in keys if k not in hallucinated_keys]
        if not kept:
            return ""
        return "[" + ", ".join(kept) + "]"

    result = re.sub(
        rf"\[({_CITE_KEY_PAT}(?:\s*[,;]\s*{_CITE_KEY_PAT})*)\]",
        _replace_markdown, result,
    )

    # Clean artifacts
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\(\s*\)", "", result)
    result = re.sub(r"\[\s*\]", "", result)

    return result

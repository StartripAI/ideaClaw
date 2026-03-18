"""Citation verification — validates that cited sources actually exist.

Resolves DOIs, arXiv IDs, PubMed IDs to verify citations are real.
Checks URL reachability as a fallback.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CitationCheck:
    """Result of verifying a single citation."""
    citation_text: str
    identifier: str  # DOI, arXiv ID, PMID, or URL
    identifier_type: str  # 'doi' | 'arxiv' | 'pmid' | 'url' | 'unknown'
    verified: bool
    resolved_title: str = ""
    resolved_url: str = ""
    detail: str = ""


def _extract_identifiers(text: str) -> List[tuple]:
    """Extract all citable identifiers from text.

    Returns list of (identifier, type) tuples.
    """
    found = []

    # DOIs: 10.xxxx/xxxx
    for m in re.finditer(r"\b(10\.\d{4,}/[^\s,;)\]]+)", text):
        found.append((m.group(1).rstrip("."), "doi"))

    # arXiv: arxiv:XXXX.XXXXX or arXiv:XXXX.XXXXX
    for m in re.finditer(r"(?:arxiv:|arXiv:)(\d{4}\.\d{4,5}(?:v\d+)?)", text, re.IGNORECASE):
        found.append((m.group(1), "arxiv"))

    # arXiv URLs
    for m in re.finditer(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", text):
        found.append((m.group(1), "arxiv"))

    # PubMed IDs: PMID:12345678 or pubmed/12345678
    for m in re.finditer(r"(?:PMID:|pubmed/)(\d{7,9})", text, re.IGNORECASE):
        found.append((m.group(1), "pmid"))

    # URLs (http/https)
    for m in re.finditer(r"(https?://[^\s,;)\]\"']+)", text):
        url = m.group(1).rstrip(".")
        # Skip if already captured as DOI/arXiv/PubMed
        if not any(ident in url for ident, _ in found):
            found.append((url, "url"))

    # Deduplicate
    seen = set()
    unique = []
    for ident, itype in found:
        key = (ident.lower(), itype)
        if key not in seen:
            seen.add(key)
            unique.append((ident, itype))

    return unique


def verify_doi(doi: str) -> CitationCheck:
    """Verify a DOI by resolving it via doi.org API.

    Uses the DOI content negotiation to get metadata as JSON.
    """
    url = f"https://doi.org/{doi}"
    try:
        req = urllib.request.Request(
            f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}",
            headers={"User-Agent": "ideaclaw/1.0 (mailto:hello@startrip.ai)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            work = data.get("message", {})
            title_parts = work.get("title", [""])
            title = title_parts[0] if title_parts else ""
            return CitationCheck(
                citation_text=doi,
                identifier=doi,
                identifier_type="doi",
                verified=True,
                resolved_title=title,
                resolved_url=url,
                detail=f"crossref_resolved type={work.get('type', 'unknown')}",
            )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError) as exc:
        return CitationCheck(
            citation_text=doi,
            identifier=doi,
            identifier_type="doi",
            verified=False,
            detail=f"doi_resolve_failed: {exc}",
        )


def verify_arxiv(arxiv_id: str) -> CitationCheck:
    """Verify an arXiv ID by checking the Atom API."""
    import xml.etree.ElementTree as ET

    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ideaclaw/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")

        # Parse Atom to check if entry exists
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(data)
        entries = root.findall("atom:entry", ns)
        if entries:
            title_el = entries[0].find("atom:title", ns)
            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            if title and "Error" not in title:
                return CitationCheck(
                    citation_text=arxiv_id,
                    identifier=arxiv_id,
                    identifier_type="arxiv",
                    verified=True,
                    resolved_title=title,
                    resolved_url=f"https://arxiv.org/abs/{arxiv_id}",
                    detail="arxiv_api_resolved",
                )

        return CitationCheck(
            citation_text=arxiv_id,
            identifier=arxiv_id,
            identifier_type="arxiv",
            verified=False,
            detail="arxiv_id_not_found",
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ET.ParseError) as exc:
        return CitationCheck(
            citation_text=arxiv_id,
            identifier=arxiv_id,
            identifier_type="arxiv",
            verified=False,
            detail=f"arxiv_resolve_failed: {exc}",
        )


def verify_pmid(pmid: str) -> CitationCheck:
    """Verify a PubMed ID by checking NCBI E-Utilities."""
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ideaclaw/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            doc = data.get("result", {}).get(pmid, {})
            title = doc.get("title", "")
            if title:
                return CitationCheck(
                    citation_text=pmid,
                    identifier=pmid,
                    identifier_type="pmid",
                    verified=True,
                    resolved_title=title,
                    resolved_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    detail="pubmed_resolved",
                )
            return CitationCheck(
                citation_text=pmid,
                identifier=pmid,
                identifier_type="pmid",
                verified=False,
                detail="pmid_not_found",
            )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return CitationCheck(
            citation_text=pmid,
            identifier=pmid,
            identifier_type="pmid",
            verified=False,
            detail=f"pmid_resolve_failed: {exc}",
        )


def verify_url(url: str) -> CitationCheck:
    """Verify a URL by checking reachability (HEAD request)."""
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "ideaclaw/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return CitationCheck(
                citation_text=url,
                identifier=url,
                identifier_type="url",
                verified=resp.status < 400,
                resolved_url=url,
                detail=f"http_{resp.status}",
            )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Try GET as fallback (some servers don't support HEAD)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ideaclaw/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return CitationCheck(
                    citation_text=url,
                    identifier=url,
                    identifier_type="url",
                    verified=resp.status < 400,
                    resolved_url=url,
                    detail=f"http_get_{resp.status}",
                )
        except (urllib.error.URLError, TimeoutError, OSError):
            return CitationCheck(
                citation_text=url,
                identifier=url,
                identifier_type="url",
                verified=False,
                detail=f"url_unreachable: {exc}",
            )


def verify_citations(text: str) -> List[CitationCheck]:
    """Extract and verify all citations from text.

    Finds DOIs, arXiv IDs, PubMed IDs, and URLs in the text,
    then resolves each one to verify it exists.

    Args:
        text: Text containing citations (markdown pack content).

    Returns:
        List of CitationCheck results, one per unique citation.
    """
    identifiers = _extract_identifiers(text)
    results = []

    for ident, itype in identifiers:
        if itype == "doi":
            results.append(verify_doi(ident))
        elif itype == "arxiv":
            results.append(verify_arxiv(ident))
        elif itype == "pmid":
            results.append(verify_pmid(ident))
        elif itype == "url":
            results.append(verify_url(ident))
        else:
            results.append(CitationCheck(
                citation_text=ident,
                identifier=ident,
                identifier_type="unknown",
                verified=False,
                detail="unrecognized_identifier_type",
            ))

    return results


def citation_summary(results: List[CitationCheck]) -> Dict[str, Any]:
    """Generate a summary of citation verification results.

    Returns dict with counts and pass/fail verdict.
    """
    if not results:
        return {
            "total": 0,
            "verified": 0,
            "failed": 0,
            "verification_rate": 0.0,
            "verdict": "NO_CITATIONS",
        }

    verified = [r for r in results if r.verified]
    failed = [r for r in results if not r.verified]
    rate = len(verified) / len(results)

    return {
        "total": len(results),
        "verified": len(verified),
        "failed": len(failed),
        "verification_rate": round(rate, 3),
        "verdict": "PASS" if rate >= 0.7 else ("PARTIAL" if rate >= 0.4 else "FAIL"),
        "by_type": {
            itype: {
                "total": sum(1 for r in results if r.identifier_type == itype),
                "verified": sum(1 for r in results if r.identifier_type == itype and r.verified),
            }
            for itype in set(r.identifier_type for r in results)
        },
        "failed_citations": [
            {"identifier": r.identifier, "type": r.identifier_type, "detail": r.detail}
            for r in failed
        ],
    }

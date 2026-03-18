"""Multi-source collector — academic APIs + web search.

Implements real API calls to:
- arXiv (free, no key needed)
- Semantic Scholar (free, optional key)
- PubMed/NCBI (free, optional key)
- OpenAlex (free, no key needed)
- Web search (DuckDuckGo / Google Scholar scrape fallback)

Design: ARC-style parallel collection with IdeaClaw source registry integration.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SourceResult:
    """A single collected source."""
    title: str
    url: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    year: Optional[int] = None
    source_api: str = ""  # arXiv | semantic_scholar | pubmed | openalex | web
    relevance_score: float = 0.0
    citation_count: int = 0
    doi: str = ""
    pdf_url: str = ""


# ---------------------------------------------------------------------------
# arXiv API (Atom XML, free, no key)
# ---------------------------------------------------------------------------

def search_arxiv(
    query: str,
    max_results: int = 20,
    sort_by: str = "relevance",
) -> List[SourceResult]:
    """Search arXiv via the free Atom API.

    Args:
        query: Search query (supports arXiv query syntax).
        max_results: Max number of results (up to 100).
        sort_by: 'relevance' or 'lastUpdatedDate' or 'submittedDate'.

    Returns:
        List of SourceResult from arXiv.
    """
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": min(max_results, 100),
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ideaclaw/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []

    # Parse Atom feed
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []

    results = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

        summary_el = entry.find("atom:summary", ns)
        abstract = (summary_el.text or "").strip() if summary_el is not None else ""

        # Get link
        link_url = ""
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            href = link.attrib.get("href", "")
            if link.attrib.get("title") == "pdf":
                pdf_url = href
            elif link.attrib.get("type") == "text/html" or (not link_url and href):
                link_url = href

        # Authors
        authors = []
        for author in entry.findall("atom:author", ns):
            name_el = author.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        # Published date → year
        published_el = entry.find("atom:published", ns)
        year = None
        if published_el is not None and published_el.text:
            m = re.match(r"(\d{4})", published_el.text)
            if m:
                year = int(m.group(1))

        # DOI
        doi_el = entry.find("arxiv:doi", ns)
        doi = (doi_el.text or "").strip() if doi_el is not None else ""

        if title:
            results.append(SourceResult(
                title=title,
                url=link_url or pdf_url,
                authors=authors,
                abstract=abstract[:1000],
                year=year,
                source_api="arxiv",
                doi=doi,
                pdf_url=pdf_url,
            ))

    return results


# ---------------------------------------------------------------------------
# Semantic Scholar API (free tier: 100 req/sec without key)
# ---------------------------------------------------------------------------

def search_semantic_scholar(
    query: str,
    max_results: int = 20,
    api_key: Optional[str] = None,
) -> List[SourceResult]:
    """Search Semantic Scholar via the Graph API.

    Args:
        query: Natural language search query.
        max_results: Max results (up to 100).
        api_key: Optional S2 API key for higher rate limits.

    Returns:
        List of SourceResult from Semantic Scholar.
    """
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": min(max_results, 100),
        "fields": "title,abstract,authors,year,citationCount,externalIds,url,openAccessPdf",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    headers = {"User-Agent": "ideaclaw/1.0"}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []

    results = []
    for paper in data.get("data", []):
        title = paper.get("title", "")
        if not title:
            continue

        authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
        ext_ids = paper.get("externalIds", {}) or {}
        doi = ext_ids.get("DOI", "")
        arxiv_id = ext_ids.get("ArXiv", "")

        pdf_info = paper.get("openAccessPdf") or {}
        pdf_url = pdf_info.get("url", "")

        paper_url = paper.get("url", "")
        if not paper_url and doi:
            paper_url = f"https://doi.org/{doi}"
        elif not paper_url and arxiv_id:
            paper_url = f"https://arxiv.org/abs/{arxiv_id}"

        results.append(SourceResult(
            title=title,
            url=paper_url,
            authors=authors,
            abstract=(paper.get("abstract") or "")[:1000],
            year=paper.get("year"),
            source_api="semantic_scholar",
            citation_count=paper.get("citationCount", 0) or 0,
            doi=doi,
            pdf_url=pdf_url,
        ))

    return results


# ---------------------------------------------------------------------------
# PubMed / NCBI E-Utilities (free, optional API key)
# ---------------------------------------------------------------------------

def search_pubmed(
    query: str,
    max_results: int = 20,
    api_key: Optional[str] = None,
) -> List[SourceResult]:
    """Search PubMed via NCBI E-Utilities.

    Args:
        query: PubMed search query.
        max_results: Max results (up to 100).
        api_key: Optional NCBI API key.

    Returns:
        List of SourceResult from PubMed.
    """
    # Step 1: eSearch to get PMIDs
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params: Dict[str, Any] = {
        "db": "pubmed",
        "term": query,
        "retmax": min(max_results, 100),
        "retmode": "json",
        "sort": "relevance",
    }
    if api_key:
        params["api_key"] = api_key

    try:
        req = urllib.request.Request(
            f"{search_url}?{urllib.parse.urlencode(params)}",
            headers={"User-Agent": "ideaclaw/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            search_data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []

    pmids = search_data.get("esearchresult", {}).get("idlist", [])
    if not pmids:
        return []

    # Step 2: eSummary to get details
    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params2: Dict[str, Any] = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }
    if api_key:
        params2["api_key"] = api_key

    time.sleep(0.35)  # Respect NCBI rate limit

    try:
        req = urllib.request.Request(
            f"{summary_url}?{urllib.parse.urlencode(params2)}",
            headers={"User-Agent": "ideaclaw/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            summary_data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []

    results = []
    for pmid in pmids:
        doc = summary_data.get("result", {}).get(pmid, {})
        if not isinstance(doc, dict):
            continue
        title = doc.get("title", "").strip()
        if not title:
            continue

        authors = []
        for a in doc.get("authors", []):
            name = a.get("name", "")
            if name:
                authors.append(name)

        # Extract year from pubdate
        pubdate = doc.get("pubdate", "")
        year = None
        m = re.match(r"(\d{4})", pubdate)
        if m:
            year = int(m.group(1))

        # DOI from articleids
        doi = ""
        for aid in doc.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
                break

        results.append(SourceResult(
            title=title,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            authors=authors,
            year=year,
            source_api="pubmed",
            doi=doi,
        ))

    return results


# ---------------------------------------------------------------------------
# OpenAlex API (free, no key needed)
# ---------------------------------------------------------------------------

def search_openalex(
    query: str,
    max_results: int = 20,
) -> List[SourceResult]:
    """Search OpenAlex for academic works.

    Args:
        query: Search query.
        max_results: Max results (up to 200).

    Returns:
        List of SourceResult from OpenAlex.
    """
    base_url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per_page": min(max_results, 200),
        "sort": "relevance_score:desc",
        "select": "id,title,authorships,publication_year,cited_by_count,doi,open_access",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ideaclaw/1.0 (mailto:hello@startrip.ai)",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []

    results = []
    for work in data.get("results", []):
        title = work.get("title", "")
        if not title:
            continue

        authors = []
        for auth in work.get("authorships", []):
            name = auth.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        doi = work.get("doi", "") or ""
        oa = work.get("open_access", {}) or {}
        pdf_url = oa.get("oa_url", "") or ""

        work_url = doi if doi.startswith("https://") else (f"https://doi.org/{doi}" if doi else work.get("id", ""))

        results.append(SourceResult(
            title=title,
            url=work_url,
            authors=authors[:10],
            year=work.get("publication_year"),
            source_api="openalex",
            citation_count=work.get("cited_by_count", 0) or 0,
            doi=doi.replace("https://doi.org/", ""),
            pdf_url=pdf_url,
        ))

    return results


# ---------------------------------------------------------------------------
# Unified multi-source collector
# ---------------------------------------------------------------------------

def collect_sources(
    query: str,
    apis: Optional[List[str]] = None,
    max_per_api: int = 15,
    config: Optional[Dict[str, Any]] = None,
) -> List[SourceResult]:
    """Collect sources from multiple academic APIs.

    Args:
        query: Search query.
        apis: List of APIs to search. Default: all available.
            Options: 'arxiv', 'semantic_scholar', 'pubmed', 'openalex'.
        max_per_api: Max results per API.
        config: Optional config with API keys:
            config.llm.semantic_scholar_key, config.llm.ncbi_key, etc.

    Returns:
        Deduplicated, ranked list of SourceResult.
    """
    if apis is None:
        apis = ["arxiv", "semantic_scholar", "openalex"]

    config = config or {}
    all_results: List[SourceResult] = []

    for api in apis:
        try:
            if api == "arxiv":
                all_results.extend(search_arxiv(query, max_results=max_per_api))
            elif api == "semantic_scholar":
                s2_key = config.get("llm", {}).get("semantic_scholar_key")
                all_results.extend(
                    search_semantic_scholar(query, max_results=max_per_api, api_key=s2_key)
                )
            elif api == "pubmed":
                ncbi_key = config.get("llm", {}).get("ncbi_key")
                all_results.extend(
                    search_pubmed(query, max_results=max_per_api, api_key=ncbi_key)
                )
            elif api == "openalex":
                all_results.extend(search_openalex(query, max_results=max_per_api))
        except Exception:  # noqa: BLE001
            continue

    # Deduplicate by DOI or title
    seen_dois: set = set()
    seen_titles: set = set()
    deduped: List[SourceResult] = []
    for r in all_results:
        key_doi = r.doi.lower().strip() if r.doi else ""
        key_title = re.sub(r"\s+", " ", r.title.lower().strip())
        if key_doi and key_doi in seen_dois:
            continue
        if key_title in seen_titles:
            continue
        if key_doi:
            seen_dois.add(key_doi)
        seen_titles.add(key_title)
        deduped.append(r)

    # Sort by citation count (desc), then year (desc)
    deduped.sort(key=lambda r: (-(r.citation_count or 0), -(r.year or 0)))

    return deduped

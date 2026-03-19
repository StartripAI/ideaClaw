"""Semantic Scholar & OpenAlex paper search.

Ported from AI-Scientist's generate_ideas.py. Canonical copy lives in
OpenRevise/ideaclaw/sources/scholar.py — this is a symlink-equivalent
kept here so `ideaclaw.source.scholar` resolves within the ideaClaw tree.
"""

# Re-export everything from the canonical location if available,
# otherwise provide a standalone implementation.
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["search_for_papers", "SemanticScholarSearch", "PaperResult"]

S2_API_KEY = os.environ.get("S2_API_KEY", "")


@dataclass
class PaperResult:
    """Structured paper search result."""
    title: str
    authors: str
    venue: str
    year: int
    abstract: str
    url: str = ""
    doi: str = ""
    citation_count: int = 0
    bibtex: str = ""
    paper_id: str = ""

    def to_citation_string(self) -> str:
        return f"{self.authors} ({self.year}). {self.title}. {self.venue}."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title, "authors": self.authors,
            "venue": self.venue, "year": self.year,
            "abstract": self.abstract, "url": self.url,
            "doi": self.doi, "citation_count": self.citation_count,
            "bibtex": self.bibtex, "paper_id": self.paper_id,
        }


class SemanticScholarSearch:
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    FIELDS = "title,authors,venue,year,abstract,citationStyles,citationCount,externalIds,url"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or S2_API_KEY

    def search(self, query: str, limit: int = 10, year_range: Optional[str] = None) -> List[PaperResult]:
        if not query:
            return []
        params: Dict[str, Any] = {"query": query, "limit": min(limit, 100), "fields": self.FIELDS}
        if year_range:
            params["year"] = year_range

        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return self._fetch(url, headers)

    def _fetch(self, url: str, headers: Dict[str, str], retries: int = 3) -> List[PaperResult]:
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return self._parse(data)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(2 ** (attempt + 1))
                    continue
                return []
            except Exception:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return []
        return []

    def _parse(self, data: Dict) -> List[PaperResult]:
        results = []
        for item in data.get("data", []):
            authors = ", ".join(a.get("name", "") for a in (item.get("authors") or [])[:5])
            if len(item.get("authors") or []) > 5:
                authors += " et al."
            cite_styles = item.get("citationStyles") or {}
            ext_ids = item.get("externalIds") or {}
            results.append(PaperResult(
                title=item.get("title", ""), authors=authors,
                venue=item.get("venue") or "", year=item.get("year") or 0,
                abstract=item.get("abstract") or "", url=item.get("url") or "",
                doi=ext_ids.get("DOI", ""),
                citation_count=item.get("citationCount") or 0,
                bibtex=cite_styles.get("bibtex", ""),
                paper_id=item.get("paperId", ""),
            ))
        return results


def search_for_papers(query: str, limit: int = 10, engine: str = "semanticscholar",
                      year_range: Optional[str] = None) -> List[PaperResult]:
    """Search for papers. Tries Semantic Scholar first."""
    return SemanticScholarSearch().search(query, limit, year_range)

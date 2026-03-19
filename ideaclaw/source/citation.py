"""Citation enrichment loop — ported from AI-Scientist."""

from __future__ import annotations
import json, logging, re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ideaclaw.source.scholar import PaperResult, search_for_papers

logger = logging.getLogger(__name__)
__all__ = ["CitationManager", "CitationRound"]


@dataclass
class CitationRound:
    round_num: int
    query: str
    description: str
    selected_papers: List[PaperResult]
    inserted: bool = False


CITATION_SYSTEM = "You are adding missing citations to a research draft. You have {total_rounds} rounds."

CITATION_IDENTIFY = '''\
Round {current_round}/{total_rounds}. Draft so far:
"""
{draft}
"""
Identify the most important missing citation. Respond JSON:
```json
{{"Description": "...", "Query": "search query"}}
```
If done, set Query to "".
'''

CITATION_SELECT = """\
Search results:
{papers}
Select best match(es). JSON:
```json
{{"Selected": [0], "Description": "how to insert"}}
```
"""


class CitationManager:
    def __init__(self, max_rounds: int = 20, engine: str = "semanticscholar"):
        self.max_rounds = max_rounds
        self.engine = engine
        self.rounds: List[CitationRound] = []

    def run_citation_loop(self, draft: str, llm_call_fn: Optional[Callable] = None) -> Tuple[str, List[CitationRound]]:
        if llm_call_fn is None:
            return draft, []

        enriched = draft
        for rnd in range(1, self.max_rounds + 1):
            sys_msg = CITATION_SYSTEM.format(total_rounds=self.max_rounds)
            usr_msg = CITATION_IDENTIFY.format(current_round=rnd, total_rounds=self.max_rounds, draft=enriched[:8000])
            resp = llm_call_fn(sys_msg, usr_msg)

            parsed = self._parse_json(resp)
            if not parsed or not parsed.get("Query"):
                break

            papers = search_for_papers(parsed["Query"], limit=5, engine=self.engine)
            if not papers:
                continue

            papers_str = "\n".join(f"{i}: {p.title}. {p.authors}. {p.venue}, {p.year}." for i, p in enumerate(papers))
            sel_resp = llm_call_fn(sys_msg, CITATION_SELECT.format(papers=papers_str))
            sel = self._parse_json(sel_resp)
            if not sel:
                continue

            selected = [papers[i] for i in sel.get("Selected", []) if 0 <= i < len(papers)]
            for p in selected:
                cite = f"- {p.to_citation_string()}"
                for hdr in ["## Sources", "## References", "## 📚 Sources"]:
                    if hdr in enriched:
                        parts = enriched.split(hdr, 1)
                        enriched = parts[0] + hdr + parts[1] + f"\n{cite}"
                        break
                else:
                    enriched += f"\n\n## References\n{cite}\n"

            self.rounds.append(CitationRound(rnd, parsed["Query"], parsed.get("Description", ""), selected, bool(selected)))

        return enriched, self.rounds

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict]:
        m = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        try:
            return json.loads(m.group(1)) if m else json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return None

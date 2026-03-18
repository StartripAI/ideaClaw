"""Benchmark runner — test packs against profile quality standards.

Supports three levels:
  L1: Structure compliance (sections present)
  L2: Evidence traceability (claims linked to sources)
  L3: PQS threshold (quality score meets pass mark)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ideaclaw.quality.loader import Profile, load_profile
from ideaclaw.quality.scorer import PackScorer, ScoreResult
from ideaclaw.quality.reviewer import PackReviewer, ReviewResult


@dataclass
class BenchmarkEntry:
    """Result for a single pack in the benchmark."""
    idea: str
    profile_id: str
    pack_path: Optional[str] = None
    l1_passed: bool = False    # Structure compliance
    l2_passed: bool = False    # Evidence traceability
    l3_passed: bool = False    # PQS threshold
    pqs: float = 0.0
    verdict: str = ""
    review_pass_rate: float = 0.0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idea": self.idea[:80],
            "profile_id": self.profile_id,
            "l1_passed": self.l1_passed,
            "l2_passed": self.l2_passed,
            "l3_passed": self.l3_passed,
            "pqs": round(self.pqs, 2),
            "verdict": self.verdict,
            "review_pass_rate": round(self.review_pass_rate, 2),
            "error": self.error,
        }


@dataclass
class BenchmarkReport:
    """Complete benchmark report."""
    total: int = 0
    l1_passed: int = 0
    l2_passed: int = 0
    l3_passed: int = 0
    avg_pqs: float = 0.0
    entries: List[BenchmarkEntry] = field(default_factory=list)
    per_domain: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "l1_passed": self.l1_passed,
            "l1_rate": f"{self.l1_passed}/{self.total}",
            "l2_passed": self.l2_passed,
            "l2_rate": f"{self.l2_passed}/{self.total}",
            "l3_passed": self.l3_passed,
            "l3_rate": f"{self.l3_passed}/{self.total}",
            "avg_pqs": round(self.avg_pqs, 2),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "per_domain": self.per_domain,
            "entries": [e.to_dict() for e in self.entries],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class BenchmarkRunner:
    """Run benchmark tests on a set of pack files."""

    def __init__(self):
        self.entries: List[BenchmarkEntry] = []

    def add_pack(
        self,
        pack_content: str,
        idea: str,
        profile_id: str,
        pack_path: Optional[str] = None,
    ) -> BenchmarkEntry:
        """Score and review a single pack."""
        entry = BenchmarkEntry(idea=idea, profile_id=profile_id, pack_path=pack_path)

        try:
            profile = load_profile(profile_id)
            scorer = PackScorer(profile)
            reviewer = PackReviewer(profile)

            # Score
            score_result = scorer.score_heuristic(pack_content)
            entry.pqs = score_result.pqs
            entry.verdict = score_result.verdict

            # Review
            review_result = reviewer.review(pack_content)
            entry.review_pass_rate = review_result.pass_rate

            # L1: Structure compliance (all required sections present)
            section_checks = [
                r for r in review_result.checklist_results
                if "Section" in r.item and "present" in r.item
            ]
            entry.l1_passed = all(r.passed for r in section_checks) if section_checks else True

            # L2: Evidence traceability (evidence markers exist and sources present)
            evidence_checks = [
                r for r in review_result.checklist_results
                if "Evidence" in r.item or "Sources" in r.item or "source" in r.item.lower()
            ]
            entry.l2_passed = any(r.passed for r in evidence_checks) if evidence_checks else (
                "✅" in pack_content or "http" in pack_content
            )

            # L3: PQS meets threshold
            entry.l3_passed = entry.pqs >= profile.pass_threshold

        except Exception as e:
            entry.error = str(e)

        self.entries.append(entry)
        return entry

    def generate_report(self) -> BenchmarkReport:
        """Generate a full benchmark report from all added packs."""
        report = BenchmarkReport()
        report.total = len(self.entries)
        report.entries = self.entries

        if not self.entries:
            return report

        report.l1_passed = sum(1 for e in self.entries if e.l1_passed)
        report.l2_passed = sum(1 for e in self.entries if e.l2_passed)
        report.l3_passed = sum(1 for e in self.entries if e.l3_passed)
        report.avg_pqs = sum(e.pqs for e in self.entries) / len(self.entries)

        # Per-domain breakdown
        domains: Dict[str, List[BenchmarkEntry]] = {}
        for e in self.entries:
            d = e.profile_id.split(".")[0]
            domains.setdefault(d, []).append(e)

        for domain, entries in sorted(domains.items()):
            report.per_domain[domain] = {
                "count": len(entries),
                "avg_pqs": round(sum(e.pqs for e in entries) / len(entries), 2),
                "l1_rate": f"{sum(1 for e in entries if e.l1_passed)}/{len(entries)}",
                "l2_rate": f"{sum(1 for e in entries if e.l2_passed)}/{len(entries)}",
                "l3_rate": f"{sum(1 for e in entries if e.l3_passed)}/{len(entries)}",
            }

        return report

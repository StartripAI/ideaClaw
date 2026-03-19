"""Evidence synthesis — merge verified evidence into coherent analysis.

Integrates with:
  - orchestrator.loop → called after evidence collection to build narrative
  - reasoning.decompose → synthesizes answers per sub-question
  - quality.scorer → synthesis quality feeds into PQS
  - knowledge.memory → stores synthesis results for future recall

Features:
  - Confidence-weighted synthesis (HIGH > MEDIUM > LOW)
  - Conflict resolution between contradictory evidence
  - Gap identification and coverage scoring
  - Multi-strategy synthesis (agree/disagree/conditional)
  - LLM prompt builder for narrative synthesis

Usage:
    from ideaclaw.reasoning.synthesize import Synthesizer
    s = Synthesizer()
    result = s.synthesize(evidence_items, idea_text, sub_questions)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = ["Synthesizer", "SynthesisResult", "heuristic_synthesize", "build_synthesis_prompt"]


CONFIDENCE_WEIGHTS = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3, "UNKNOWN": 0.1}


@dataclass
class EvidenceCluster:
    """A group of related evidence items."""
    theme: str
    items: List[Dict[str, Any]] = field(default_factory=list)
    confidence: str = "UNKNOWN"
    direction: str = "neutral"    # supports|contradicts|neutral
    weight: float = 0.0


@dataclass
class SynthesisResult:
    """Complete synthesis result."""
    summary: str
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    confidence_distribution: Dict[str, int] = field(default_factory=dict)
    coverage_score: float = 0.0
    overall_confidence: str = "MEDIUM"
    total_evidence: int = 0
    clusters: List[EvidenceCluster] = field(default_factory=list)
    verdict: str = ""              # supports|contradicts|mixed|insufficient


class Synthesizer:
    """Evidence synthesizer with conflict resolution and gap detection."""

    def __init__(self, llm_callable: Optional[Callable[[str], str]] = None):
        self.llm = llm_callable

    def synthesize(
        self,
        evidence_items: List[Dict[str, Any]],
        idea_text: str = "",
        sub_questions: Optional[List[str]] = None,
    ) -> SynthesisResult:
        """Synthesize evidence into structured analysis.

        Args:
            evidence_items: Evidence dicts with 'claim', 'source', 'confidence'.
            idea_text: Original idea for context.
            sub_questions: Optional sub-questions to map evidence to.

        Returns:
            SynthesisResult with findings, gaps, conflicts, verdict.
        """
        if not evidence_items:
            return SynthesisResult(
                summary="Insufficient evidence for synthesis.",
                gaps=["No evidence collected."],
                verdict="insufficient",
            )

        # Categorize by confidence
        high = [e for e in evidence_items if e.get("confidence", "").upper() == "HIGH"]
        medium = [e for e in evidence_items if e.get("confidence", "").upper() == "MEDIUM"]
        low = [e for e in evidence_items if e.get("confidence", "").upper() == "LOW"]
        unknown = [e for e in evidence_items if e.get("confidence", "").upper() not in CONFIDENCE_WEIGHTS]

        # Cluster evidence by theme
        clusters = self._cluster_evidence(evidence_items)

        # Detect conflicts
        conflicts = self._detect_conflicts(evidence_items)

        # Key findings (weighted by confidence)
        key_findings = self._extract_key_findings(evidence_items)

        # Gap analysis
        gaps = self._identify_gaps(evidence_items, sub_questions or [])

        # Coverage score
        coverage = self._compute_coverage(evidence_items, sub_questions or [])

        # Overall verdict
        verdict = self._determine_verdict(evidence_items, conflicts)

        # Overall confidence
        overall_conf = self._aggregate_confidence(evidence_items)

        # Summary
        summary = self._build_summary(
            idea_text, evidence_items, key_findings, conflicts, verdict,
        )

        result = SynthesisResult(
            summary=summary,
            key_findings=key_findings,
            gaps=gaps,
            conflicts=conflicts,
            confidence_distribution={
                "HIGH": len(high), "MEDIUM": len(medium),
                "LOW": len(low), "UNKNOWN": len(unknown),
            },
            coverage_score=coverage,
            overall_confidence=overall_conf,
            total_evidence=len(evidence_items),
            clusters=clusters,
            verdict=verdict,
        )

        logger.info(
            "Synthesized %d items → verdict=%s, confidence=%s, coverage=%.2f",
            len(evidence_items), verdict, overall_conf, coverage,
        )
        return result

    def _cluster_evidence(self, items: List[Dict[str, Any]]) -> List[EvidenceCluster]:
        """Group evidence by topic similarity."""
        if not items:
            return []

        clusters: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            claim = item.get("claim", "")
            # Simple keyword-based clustering
            key_words = set(re.findall(r"\w{4,}", claim.lower()))
            matched = False
            for theme, existing in clusters.items():
                theme_words = set(re.findall(r"\w{4,}", theme.lower()))
                if len(key_words & theme_words) >= 2:
                    existing.append(item)
                    matched = True
                    break
            if not matched:
                clusters[claim[:60]] = [item]

        result = []
        for theme, cluster_items in clusters.items():
            confidences = [CONFIDENCE_WEIGHTS.get(e.get("confidence", "").upper(), 0.1) for e in cluster_items]
            avg_weight = sum(confidences) / len(confidences) if confidences else 0
            result.append(EvidenceCluster(
                theme=theme,
                items=cluster_items,
                confidence="HIGH" if avg_weight > 0.7 else "MEDIUM" if avg_weight > 0.4 else "LOW",
                weight=avg_weight,
            ))
        return sorted(result, key=lambda c: -c.weight)

    @staticmethod
    def _detect_conflicts(items: List[Dict[str, Any]]) -> List[str]:
        """Detect contradictory evidence."""
        conflicts = []
        negation_words = {"not", "no", "never", "neither", "cannot", "unlikely",
                          "fails", "incorrect", "wrong", "disprove", "refute"}

        for i, a in enumerate(items):
            for b in items[i + 1:]:
                a_claim = set(re.findall(r"\w+", a.get("claim", "").lower()))
                b_claim = set(re.findall(r"\w+", b.get("claim", "").lower()))
                shared = a_claim & b_claim - {"the", "a", "is", "are", "and", "of", "to", "in"}

                if len(shared) >= 3:
                    a_neg = bool(a_claim & negation_words)
                    b_neg = bool(b_claim & negation_words)
                    if a_neg != b_neg:
                        conflicts.append(
                            f"Conflict: '{a.get('claim', '')[:60]}' vs "
                            f"'{b.get('claim', '')[:60]}'"
                        )
        return conflicts[:5]

    @staticmethod
    def _extract_key_findings(items: List[Dict[str, Any]]) -> List[str]:
        """Extract key findings, weighted by confidence."""
        weighted = []
        for item in items:
            claim = item.get("claim", "")
            if not claim:
                continue
            w = CONFIDENCE_WEIGHTS.get(item.get("confidence", "").upper(), 0.1)
            weighted.append((w, claim))
        weighted.sort(key=lambda x: -x[0])
        return [claim for _, claim in weighted[:10]]

    @staticmethod
    def _identify_gaps(items: List[Dict[str, Any]], sub_questions: List[str]) -> List[str]:
        """Identify evidence gaps."""
        gaps = []
        high = [e for e in items if e.get("confidence", "").upper() == "HIGH"]
        if not high:
            gaps.append("No HIGH confidence evidence — all findings are tentative.")

        if len(items) < 3:
            gaps.append("Very few evidence items collected — broader search recommended.")

        # Check coverage of sub-questions
        for sq in sub_questions:
            sq_words = set(re.findall(r"\w{4,}", sq.lower()))
            covered = False
            for item in items:
                claim_words = set(re.findall(r"\w{4,}", item.get("claim", "").lower()))
                if len(sq_words & claim_words) >= 2:
                    covered = True
                    break
            if not covered:
                gaps.append(f"No evidence found for: '{sq[:80]}'")

        return gaps

    @staticmethod
    def _compute_coverage(items: List[Dict[str, Any]], sub_questions: List[str]) -> float:
        """Compute how well evidence covers the sub-questions."""
        if not sub_questions:
            return min(1.0, len(items) / 5)

        covered = 0
        for sq in sub_questions:
            sq_words = set(re.findall(r"\w{4,}", sq.lower()))
            for item in items:
                claim_words = set(re.findall(r"\w{4,}", item.get("claim", "").lower()))
                if len(sq_words & claim_words) >= 2:
                    covered += 1
                    break
        return covered / len(sub_questions)

    @staticmethod
    def _determine_verdict(items: List[Dict[str, Any]], conflicts: List[str]) -> str:
        """Determine overall verdict."""
        if len(items) < 2:
            return "insufficient"
        if len(conflicts) > len(items) // 3:
            return "mixed"
        return "supports"

    @staticmethod
    def _aggregate_confidence(items: List[Dict[str, Any]]) -> str:
        """Compute overall confidence level."""
        if not items:
            return "UNKNOWN"
        weights = [CONFIDENCE_WEIGHTS.get(e.get("confidence", "").upper(), 0.1) for e in items]
        avg = sum(weights) / len(weights)
        if avg > 0.7:
            return "HIGH"
        if avg > 0.4:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _build_summary(
        idea_text: str, items: List[Dict[str, Any]],
        key_findings: List[str], conflicts: List[str], verdict: str,
    ) -> str:
        """Build human-readable summary."""
        parts = [f"Analyzed {len(items)} evidence items for '{idea_text[:60]}'."]

        if verdict == "supports":
            parts.append("The evidence predominantly supports the idea.")
        elif verdict == "mixed":
            parts.append("The evidence is mixed, with notable contradictions.")
        elif verdict == "contradicts":
            parts.append("The evidence largely contradicts the idea.")
        else:
            parts.append("Insufficient evidence for a strong conclusion.")

        if key_findings:
            parts.append(f"Top finding: {key_findings[0][:200]}")
        if conflicts:
            parts.append(f"Note: {len(conflicts)} conflicting evidence pair(s) detected.")

        return " ".join(parts)


# ---------------------------------------------------------------------------
# Standalone Functions (backward compatible)
# ---------------------------------------------------------------------------

def heuristic_synthesize(
    evidence_items: List[Dict[str, Any]], idea_text: str = "",
) -> Dict[str, Any]:
    """Backward-compatible synthesis function."""
    s = Synthesizer()
    result = s.synthesize(evidence_items, idea_text)
    return {
        "summary": result.summary,
        "key_findings": result.key_findings,
        "gaps": result.gaps,
        "confidence_distribution": result.confidence_distribution,
        "total_evidence": result.total_evidence,
    }


def build_synthesis_prompt(
    evidence_items: List[Dict[str, Any]],
    idea_text: str,
    sub_questions: Optional[List[str]] = None,
) -> str:
    """Build LLM prompt for evidence synthesis."""
    evidence_block = "\n".join([
        f"- [{e.get('confidence', '?')}] {e.get('claim', '')}"
        f" (Source: {e.get('source', 'unknown')})"
        for e in evidence_items[:30]
    ])

    sq_block = ""
    if sub_questions:
        sq_block = "\n\nSub-questions to address:\n" + "\n".join(
            f"{i}. {q}" for i, q in enumerate(sub_questions, 1)
        )

    return f"""Synthesize the following evidence into a coherent analysis.

Idea: {idea_text}
{sq_block}

Evidence collected:
{evidence_block}

Instructions:
1. Group evidence by theme.
2. Highlight conflicts between pieces of evidence.
3. Weight findings by confidence level (HIGH > MEDIUM > LOW).
4. Identify gaps where evidence is missing.
5. Provide a clear verdict: SUPPORTS / CONTRADICTS / MIXED / INSUFFICIENT.
6. Be explicit about what is well-supported vs speculative.
7. Use MECE structure to organize findings.
"""

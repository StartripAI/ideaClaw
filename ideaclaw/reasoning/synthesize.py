"""Evidence synthesis — merges verified evidence into coherent analysis.

Provides heuristic synthesis templates and LLM prompt builders.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def heuristic_synthesize(
    evidence_items: List[Dict[str, Any]],
    idea_text: str = "",
) -> Dict[str, Any]:
    """Synthesize evidence items into a structured analysis.

    Args:
        evidence_items: List of evidence dicts with 'claim', 'source', 'confidence'.
        idea_text: Original idea for context.

    Returns:
        Synthesis dict with 'summary', 'key_findings', 'gaps', 'confidence_distribution'.
    """
    if not evidence_items:
        return {
            "summary": "Insufficient evidence for synthesis.",
            "key_findings": [],
            "gaps": ["No evidence collected."],
            "confidence_distribution": {},
        }

    # Categorize by confidence
    high = [e for e in evidence_items if e.get("confidence", "").upper() == "HIGH"]
    medium = [e for e in evidence_items if e.get("confidence", "").upper() == "MEDIUM"]
    low = [e for e in evidence_items if e.get("confidence", "").upper() == "LOW"]
    unknown = [e for e in evidence_items if e.get("confidence", "").upper() not in {"HIGH", "MEDIUM", "LOW"}]

    # Key findings (from high-confidence evidence)
    key_findings = [e.get("claim", "") for e in (high + medium)[:10] if e.get("claim")]

    # Gaps (from low-confidence or missing areas)
    gaps = []
    if low:
        gaps.append(f"{len(low)} claims have LOW confidence and need stronger evidence.")
    if not high:
        gaps.append("No HIGH confidence claims found — all findings are tentative.")

    # Summary
    total = len(evidence_items)
    summary_parts = [
        f"Analyzed {total} evidence items for '{idea_text[:60]}...'.",
        f"Confidence distribution: HIGH={len(high)}, MEDIUM={len(medium)}, LOW={len(low)}.",
    ]
    if key_findings:
        summary_parts.append(f"Key finding: {key_findings[0][:200]}")

    return {
        "summary": " ".join(summary_parts),
        "key_findings": key_findings,
        "gaps": gaps,
        "confidence_distribution": {
            "HIGH": len(high),
            "MEDIUM": len(medium),
            "LOW": len(low),
            "UNKNOWN": len(unknown),
        },
        "total_evidence": total,
    }


def build_synthesis_prompt(
    evidence_items: List[Dict[str, Any]],
    idea_text: str,
    sub_questions: List[str] = None,
) -> str:
    """Build LLM prompt for evidence synthesis.

    Returns the user prompt to synthesize evidence into a coherent analysis.
    """
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
1. Identify the strongest findings (HIGH confidence claims).
2. Flag gaps where evidence is weak or missing.
3. Synthesize into a clear narrative.
4. Be explicit about what is well-supported vs speculative.
5. Use MECE structure to organize findings.
"""

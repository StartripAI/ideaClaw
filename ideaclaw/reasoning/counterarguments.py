"""Counterargument generator — devil's advocate for risk identification.

Generates structured counterarguments using both heuristic patterns and LLM prompts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Counterargument:
    """A structured counterargument."""
    claim: str
    counter: str
    severity: str = "MEDIUM"  # LOW | MEDIUM | HIGH | CRITICAL
    category: str = ""  # risk | feasibility | evidence | ethical | cost | scalability
    mitigation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "counter": self.counter,
            "severity": self.severity,
            "category": self.category,
            "mitigation": self.mitigation,
        }


# Domain-specific counterargument patterns
COUNTER_PATTERNS = {
    "cost": [
        "Hidden costs may exceed initial estimates by 2-3x",
        "Opportunity cost of this commitment vs alternatives",
        "Maintenance and ongoing operational costs not accounted for",
    ],
    "risk": [
        "What if key assumptions prove incorrect?",
        "Single point of failure risk",
        "Regulatory or compliance changes could invalidate this approach",
    ],
    "feasibility": [
        "Timeline may be unrealistic given current resources",
        "Technical complexity is being underestimated",
        "Required expertise may not be available",
    ],
    "evidence": [
        "Sample sizes in cited studies may be too small",
        "Correlation is being conflated with causation",
        "Publication bias in the evidence base",
        "Evidence from different contexts may not transfer",
    ],
    "scalability": [
        "This approach may not scale beyond the initial use case",
        "Network effects or dependencies not considered",
        "Performance degradation at scale",
    ],
    "ethical": [
        "Privacy and data protection concerns",
        "Fairness and bias implications",
        "Environmental impact not considered",
    ],
}


def generate_heuristic_counterarguments(
    idea_text: str,
    key_findings: List[str] = None,
) -> List[Counterargument]:
    """Generate counterarguments using heuristic patterns.

    Args:
        idea_text: The original idea.
        key_findings: High-confidence findings to challenge.

    Returns:
        List of Counterargument objects.
    """
    lower = idea_text.lower()
    counters: List[Counterargument] = []

    # Always include cost and risk
    for category in ["cost", "risk", "evidence"]:
        patterns = COUNTER_PATTERNS.get(category, [])
        for pattern in patterns[:2]:
            counters.append(Counterargument(
                claim=idea_text[:100],
                counter=pattern,
                severity="MEDIUM",
                category=category,
            ))

    # Context-specific
    if any(w in lower for w in ["invest", "buy", "cost", "budget", "spend"]):
        for p in COUNTER_PATTERNS["cost"]:
            counters.append(Counterargument(
                claim="Financial decision",
                counter=p,
                severity="HIGH",
                category="cost",
            ))

    if any(w in lower for w in ["migrate", "switch", "change", "adopt"]):
        for p in COUNTER_PATTERNS["feasibility"][:2]:
            counters.append(Counterargument(
                claim="Technology migration",
                counter=p,
                severity="MEDIUM",
                category="feasibility",
            ))

    if any(w in lower for w in ["ai", "ml", "algorithm", "model", "data"]):
        for p in COUNTER_PATTERNS["ethical"][:2]:
            counters.append(Counterargument(
                claim="AI/ML application",
                counter=p,
                severity="HIGH",
                category="ethical",
            ))

    # Challenge key findings
    if key_findings:
        for finding in key_findings[:3]:
            counters.append(Counterargument(
                claim=finding[:100],
                counter=f"This finding may not hold in all contexts: {finding[:60]}...",
                severity="MEDIUM",
                category="evidence",
            ))

    # Deduplicate
    seen = set()
    unique = []
    for c in counters:
        key = c.counter.lower()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique[:15]


def build_counterargument_prompt(
    idea_text: str,
    synthesis: str,
    key_findings: List[str] = None,
) -> str:
    """Build LLM prompt for counterargument generation.

    Returns the user prompt for generating devil's advocate counterarguments.
    """
    findings_block = ""
    if key_findings:
        findings_block = "\n\nKey findings to challenge:\n" + "\n".join(
            f"- {f}" for f in key_findings[:10]
        )

    return f"""Act as a devil's advocate and generate strong counterarguments for the following idea and its supporting evidence.

Idea: {idea_text}

Evidence synthesis:
{synthesis}
{findings_block}

For each counterargument, provide:
1. The claim being challenged
2. The counterargument
3. Severity (LOW / MEDIUM / HIGH / CRITICAL)
4. Category (cost / risk / feasibility / evidence / ethical / scalability)
5. Potential mitigation

Generate 5-10 diverse counterarguments, prioritizing the strongest ones.
"""

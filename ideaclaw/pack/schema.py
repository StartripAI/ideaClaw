"""Pack type schema definitions."""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class PackTypeInfo(NamedTuple):
    """Metadata for a pack type."""
    name: str
    description: str
    template: str  # Jinja2 template filename
    sections: list[str]


class PackType(Enum):
    """Supported pack types."""

    DECISION = PackTypeInfo(
        name="decision",
        description="Decision analysis — should I do X?",
        template="decision.md.j2",
        sections=["conclusion", "pros_and_cons", "reasoning", "risks", "uncertainties", "action_items", "sources"],
    )

    PROPOSAL = PackTypeInfo(
        name="proposal",
        description="Proposal document — here's my plan for X",
        template="proposal.md.j2",
        sections=["executive_summary", "background", "proposal", "justification", "risks", "action_plan", "sources"],
    )

    COMPARISON = PackTypeInfo(
        name="comparison",
        description="Structured comparison — A vs B",
        template="comparison.md.j2",
        sections=["summary", "comparison_matrix", "analysis", "recommendation", "caveats", "sources"],
    )

    BRIEF = PackTypeInfo(
        name="brief",
        description="Brief document — summary, memo, report",
        template="brief.md.j2",
        sections=["summary", "key_points", "details", "implications", "sources"],
    )

    STUDY = PackTypeInfo(
        name="study",
        description="Deep analysis — industry, trend, or market study",
        template="study.md.j2",
        sections=["executive_summary", "methodology", "findings", "analysis", "limitations", "conclusions", "sources"],
    )

    @property
    def info(self) -> PackTypeInfo:
        return self.value

    @classmethod
    def from_string(cls, name: str) -> "PackType":
        """Look up pack type by name string."""
        for pt in cls:
            if pt.info.name == name:
                return pt
        raise ValueError(f"Unknown pack type: {name}. Valid types: {[p.info.name for p in cls]}")

    @classmethod
    def auto_detect(cls, idea_text: str) -> "PackType":
        """Auto-detect pack type from idea text.

        TODO: Implement LLM-based detection. For now, default to DECISION.
        """
        lower = idea_text.lower()
        if any(w in lower for w in ["compare", "vs", "versus", "or", "which"]):
            return cls.COMPARISON
        if any(w in lower for w in ["should", "worth", "good idea", "recommend"]):
            return cls.DECISION
        if any(w in lower for w in ["plan", "pitch", "proposal", "apply"]):
            return cls.PROPOSAL
        if any(w in lower for w in ["analysis", "trend", "market", "industry", "research"]):
            return cls.STUDY
        return cls.DECISION  # Default

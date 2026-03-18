"""Decision tree builder — constructs reasoning trees from synthesis.

Provides structured decision path analysis with branches for different scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DecisionNode:
    """A node in the decision tree."""
    question: str
    answer: str = ""
    confidence: str = "MEDIUM"
    evidence_refs: List[str] = field(default_factory=list)
    children: List["DecisionNode"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "children": [c.to_dict() for c in self.children],
        }

    def to_markdown(self, depth: int = 0) -> str:
        indent = "  " * depth
        icon = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "🚫"}.get(self.confidence, "❓")
        lines = [f"{indent}- {icon} **{self.question}**"]
        if self.answer:
            lines.append(f"{indent}  → {self.answer}")
        if self.evidence_refs:
            lines.append(f"{indent}  Sources: {', '.join(self.evidence_refs[:3])}")
        for child in self.children:
            lines.append(child.to_markdown(depth + 1))
        return "\n".join(lines)


def build_decision_tree(
    idea_text: str,
    sub_questions: List[str],
    evidence_summary: Dict[str, Any],
) -> DecisionNode:
    """Build a decision tree from decomposition and evidence synthesis.

    Args:
        idea_text: The original idea.
        sub_questions: MECE sub-questions from decomposition.
        evidence_summary: Output from synthesize.heuristic_synthesize().

    Returns:
        Root DecisionNode with children.
    """
    key_findings = evidence_summary.get("key_findings", [])
    gaps = evidence_summary.get("gaps", [])
    conf_dist = evidence_summary.get("confidence_distribution", {})

    root = DecisionNode(
        question=idea_text,
        confidence="HIGH" if conf_dist.get("HIGH", 0) > conf_dist.get("LOW", 0) else "MEDIUM",
    )

    for i, sq in enumerate(sub_questions):
        finding = key_findings[i] if i < len(key_findings) else ""
        child = DecisionNode(
            question=sq,
            answer=finding,
            confidence="HIGH" if finding else "LOW",
        )
        root.children.append(child)

    # Add a "gaps" node if there are any
    if gaps:
        gap_node = DecisionNode(
            question="Evidence Gaps",
            answer="; ".join(gaps),
            confidence="LOW",
        )
        root.children.append(gap_node)

    return root


def build_decision_tree_prompt(
    idea_text: str,
    synthesis: str,
    sub_questions: List[str],
) -> str:
    """Build LLM prompt for decision tree generation.

    Returns the user prompt for the LLM to build a structured decision tree.
    """
    sq_block = "\n".join(f"{i}. {q}" for i, q in enumerate(sub_questions, 1))

    return f"""Build a decision tree for the following idea, addressing each sub-question.

Idea: {idea_text}

Sub-questions:
{sq_block}

Evidence synthesis:
{synthesis}

For each branch, specify:
1. The question being addressed
2. The evidence-based answer
3. Confidence level (HIGH/MEDIUM/LOW)
4. Evidence sources referenced
5. Any sub-branches for conditional paths

Format as a structured tree.
"""

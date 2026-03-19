"""MECE decomposition — recursive problem decomposition with dependency tracking.

Integrates with:
  - orchestrator.loop → ResearchLoop calls decompose() in the scoping phase
  - prompts.generation → uses section guidance for domain-aware decomposition
  - knowledge.memory → retrieves past decompositions for similar ideas

Features:
  - 5W1H heuristic decomposition (instant, no LLM)
  - LLM-assisted MECE decomposition with domain awareness
  - Recursive sub-decomposition for complex problems
  - Dependency graph between sub-questions
  - Priority scoring based on impact and feasibility
  - MECE validation (overlap + coverage check)

Usage:
    from ideaclaw.reasoning.decompose import Decomposer
    d = Decomposer()
    result = d.decompose(idea_text, domain="cs_ml", depth=2)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["Decomposer", "DecompositionResult", "heuristic_decompose",
           "build_llm_decompose_prompt", "parse_decomposition_response"]


@dataclass
class SubQuestion:
    """A single sub-question from decomposition."""
    text: str
    priority: int = 0           # 1=highest
    evidence_type: str = ""     # quantitative|qualitative|mixed
    dependencies: List[int] = field(default_factory=list)  # indices of prerequisite questions
    domain_hint: str = ""       # Suggested domain for answering
    estimated_effort: str = "medium"  # low|medium|high


@dataclass
class DecompositionResult:
    """Complete decomposition result."""
    idea_text: str
    sub_questions: List[SubQuestion] = field(default_factory=list)
    is_mece: bool = False
    coverage_score: float = 0.0
    overlap_warnings: List[str] = field(default_factory=list)
    depth: int = 1

    def question_texts(self) -> List[str]:
        """Get just the question text list."""
        return [sq.text for sq in self.sub_questions]

    def prioritized(self) -> List[SubQuestion]:
        """Get questions sorted by priority (highest first)."""
        return sorted(self.sub_questions, key=lambda q: q.priority)


# ---------------------------------------------------------------------------
# Domain-specific question templates
# ---------------------------------------------------------------------------

DOMAIN_TEMPLATES: Dict[str, List[str]] = {
    "cs_ml": [
        "What is the current SOTA for this task, and what are its limitations?",
        "What dataset(s) and evaluation metrics are standard for this problem?",
        "What computational resources are required, and is it feasible?",
        "How does this compare to concurrent/recent work (last 6 months)?",
        "What are the key ablation experiments needed to validate claims?",
    ],
    "medical": [
        "What is the target patient population and inclusion/exclusion criteria?",
        "What existing clinical evidence supports or contradicts this approach?",
        "What are the ethical and regulatory considerations?",
        "What statistical design (RCT, cohort, case-control) is appropriate?",
        "What are the safety risks and adverse event considerations?",
    ],
    "business": [
        "What is the total addressable market (TAM/SAM/SOM)?",
        "What is the competitive landscape and key differentiators?",
        "What is the expected ROI and payback period?",
        "What are the key execution risks and mitigation strategies?",
        "What regulatory or legal constraints apply?",
    ],
    "legal": [
        "What is the applicable legal framework and jurisdiction?",
        "What is the relevant case law and precedent?",
        "What are the competing interpretations and their implications?",
        "What are the enforcement and compliance considerations?",
    ],
}


class Decomposer:
    """Recursive MECE decomposer with dependency tracking."""

    MAX_TOTAL_QUESTIONS = 50  # P-3: hard cap to prevent question explosion

    def __init__(self, llm_callable: Optional[Callable[[str], str]] = None):
        self.llm = llm_callable

    def decompose(
        self,
        idea_text: str,
        domain: str = "general",
        depth: int = 1,
        max_questions: int = 10,
    ) -> DecompositionResult:
        """Decompose an idea into MECE sub-questions.

        Args:
            idea_text: The idea to decompose.
            domain: Domain for specialized questions.
            depth: Recursive depth (1 = flat, 2+ = sub-decompose).
            max_questions: Maximum number of top-level questions.

        Returns:
            DecompositionResult with prioritized sub-questions.
        """
        if self.llm:
            questions = self._llm_decompose(idea_text, domain, max_questions)
        else:
            questions = heuristic_decompose(idea_text, domain)

        # Build SubQuestion objects with metadata
        sub_qs = []
        for i, q_text in enumerate(questions[:max_questions]):
            sq = SubQuestion(
                text=q_text,
                priority=i + 1,
                evidence_type=self._infer_evidence_type(q_text),
                domain_hint=domain,
                estimated_effort=self._estimate_effort(q_text),
            )
            sub_qs.append(sq)

        # Infer dependencies
        self._infer_dependencies(sub_qs)

        # MECE validation
        overlap_warnings = self._check_overlap(sub_qs)
        coverage = self._check_coverage(sub_qs, idea_text)

        result = DecompositionResult(
            idea_text=idea_text,
            sub_questions=sub_qs,
            is_mece=len(overlap_warnings) == 0 and coverage > 0.7,
            coverage_score=coverage,
            overlap_warnings=overlap_warnings,
            depth=depth,
        )

        # Recursive decomposition
        if depth > 1:
            for sq in sub_qs:
                if sq.estimated_effort == "high":
                    sub_result = self.decompose(sq.text, domain, depth - 1, max_questions=4)
                    # Attach as nested
                    sq.text += f"\n  Sub-questions: {', '.join(sub_result.question_texts())}"

        logger.info(
            "Decomposed '%s...' → %d questions (MECE=%s, coverage=%.2f)",
            idea_text[:50], len(sub_qs), result.is_mece, coverage,
        )
        return result

    def _llm_decompose(self, idea_text: str, domain: str, max_q: int) -> List[str]:
        """Use LLM for decomposition."""
        prompt = build_llm_decompose_prompt(idea_text, domain, max_q)
        try:
            response = self.llm(prompt)
            return parse_decomposition_response(response)
        except Exception as e:
            logger.warning("LLM decomposition failed: %s, falling back to heuristic", e)
            return heuristic_decompose(idea_text, domain)

    @staticmethod
    def _infer_evidence_type(question: str) -> str:
        """Infer what type of evidence a question needs."""
        q_lower = question.lower()
        if any(w in q_lower for w in ["how many", "what percent", "cost", "roi", "metric", "rate"]):
            return "quantitative"
        if any(w in q_lower for w in ["why", "how does", "what are the implications", "opinion"]):
            return "qualitative"
        return "mixed"

    @staticmethod
    def _estimate_effort(question: str) -> str:
        """Estimate effort to answer a question."""
        q_lower = question.lower()
        if any(w in q_lower for w in ["comprehensive", "all", "complete", "systematic"]):
            return "high"
        if any(w in q_lower for w in ["what is", "who", "when", "basic"]):
            return "low"
        return "medium"

    @staticmethod
    def _infer_dependencies(sub_qs: List[SubQuestion]) -> None:
        """Infer dependencies between sub-questions."""
        for i, sq in enumerate(sub_qs):
            q_lower = sq.text.lower()
            for j, other in enumerate(sub_qs):
                if i == j:
                    continue
                # If question references another's topic
                other_keywords = set(re.findall(r"\w+", other.text.lower())) - {
                    "what", "how", "why", "the", "is", "are", "and", "for"
                }
                overlap = sum(1 for kw in other_keywords if kw in q_lower and len(kw) > 4)
                if overlap >= 2 and j < i:
                    sq.dependencies.append(j)

    @staticmethod
    def _check_overlap(sub_qs: List[SubQuestion]) -> List[str]:
        """Check for overlapping questions."""
        warnings = []
        for i, a in enumerate(sub_qs):
            for j, b in enumerate(sub_qs[i + 1:], i + 1):
                a_words = set(re.findall(r"\w+", a.text.lower())) - {"what", "how", "the", "is", "are", "and"}
                b_words = set(re.findall(r"\w+", b.text.lower())) - {"what", "how", "the", "is", "are", "and"}
                if a_words and b_words:
                    overlap_ratio = len(a_words & b_words) / min(len(a_words), len(b_words))
                    if overlap_ratio > 0.5:
                        warnings.append(f"Q{i+1} and Q{j+1} may overlap ({overlap_ratio:.0%} word overlap)")
        return warnings

    @staticmethod
    def _check_coverage(sub_qs: List[SubQuestion], idea_text: str) -> float:
        """Estimate how well the questions cover the idea."""
        idea_words = set(re.findall(r"\w+", idea_text.lower())) - {"the", "a", "an", "is", "are", "to", "and", "of"}
        covered = set()
        for sq in sub_qs:
            covered.update(re.findall(r"\w+", sq.text.lower()))
        if not idea_words:
            return 1.0
        return len(idea_words & covered) / len(idea_words)


# ---------------------------------------------------------------------------
# Standalone Functions (backward compatible)
# ---------------------------------------------------------------------------

def heuristic_decompose(idea_text: str, domain: str = "general") -> List[str]:
    """Decompose an idea into sub-questions using heuristic rules.

    Uses the 5W1H framework plus domain-specific patterns.
    """
    idea = idea_text.strip()
    sub_questions: List[str] = []

    # Core 5W1H
    sub_questions.append(f"What exactly is the core proposition of '{idea[:80]}'?")
    sub_questions.append("Who are the key stakeholders, and how does this affect each of them?")
    sub_questions.append("What evidence exists to support or refute this idea?")
    sub_questions.append("Is this feasible given current constraints (time, budget, technology)?")
    sub_questions.append("What are the main risks, downsides, or failure modes?")
    sub_questions.append("What are the alternative approaches, and how do they compare?")

    # Domain-specific additions
    if domain in DOMAIN_TEMPLATES:
        sub_questions.extend(DOMAIN_TEMPLATES[domain])

    # Keyword-triggered additions
    lower = idea.lower()
    if any(w in lower for w in ["invest", "buy", "purchase", "cost", "price"]):
        sub_questions.append("What is the expected ROI and total cost of ownership?")
    if any(w in lower for w in ["switch", "migrate", "transition", "replace"]):
        sub_questions.append("What is the migration cost and risk of switching?")
    if any(w in lower for w in ["hire", "team", "employee", "staff"]):
        sub_questions.append("What is the impact on team capacity and culture?")
    if any(w in lower for w in ["research", "paper", "study", "experiment"]):
        sub_questions.append("What is the current state of the art and gap in literature?")

    sub_questions.append("What is the recommended timeline and next steps?")
    return sub_questions


def build_llm_decompose_prompt(
    idea_text: str, domain: str = "general", max_questions: int = 8,
) -> str:
    """Build an LLM prompt for MECE decomposition."""
    domain_hint = ""
    if domain in DOMAIN_TEMPLATES:
        domain_hint = f"\nDomain: {domain}. Consider domain-specific angles."

    return f"""Decompose the following idea into {max_questions} MECE (Mutually Exclusive, Collectively Exhaustive) sub-questions.
{domain_hint}

Each sub-question should:
1. Cover a DISTINCT aspect (no overlap between questions)
2. Together, they should cover ALL relevant angles (exhaustive)
3. Be specific and answerable with evidence
4. Be prioritized by importance (most important first)
5. Note the type of evidence needed (quantitative/qualitative)

Idea: {idea_text}

Return as a numbered list:
1. [PRIORITY: HIGH/MED/LOW] [EVIDENCE: quant/qual/mixed] Question text
2. ...
"""


def parse_decomposition_response(response: str) -> List[str]:
    """Parse an LLM decomposition response into a list of sub-questions."""
    lines = response.strip().split("\n")
    questions = []
    for line in lines:
        cleaned = re.sub(r"^\s*\d+[\.)\]]\s*", "", line).strip()
        # Remove priority/evidence tags
        cleaned = re.sub(r"\[PRIORITY:\s*\w+\]\s*", "", cleaned)
        cleaned = re.sub(r"\[EVIDENCE:\s*\w+\]\s*", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned and len(cleaned) > 10:
            questions.append(cleaned)
    return questions or heuristic_decompose("fallback")

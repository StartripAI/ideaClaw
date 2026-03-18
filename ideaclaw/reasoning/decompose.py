"""MECE decomposition — splits ideas into mutually exclusive, collectively exhaustive sub-questions.

Provides both heuristic decomposition and LLM-assisted decomposition.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def heuristic_decompose(idea_text: str) -> List[str]:
    """Decompose an idea into sub-questions using heuristic rules.

    Uses the 5W1H framework (What, Why, Who, When, Where, How) plus
    domain-specific decomposition patterns.

    Returns:
        List of sub-questions (typically 4-8).
    """
    idea = idea_text.strip()
    sub_questions: List[str] = []

    # 1. Core question
    sub_questions.append(f"What exactly is the core proposition of '{idea[:80]}'?")

    # 2. Stakeholder analysis
    sub_questions.append("Who are the key stakeholders, and how does this affect each of them?")

    # 3. Evidence requirements
    sub_questions.append("What evidence exists to support or refute this idea?")

    # 4. Feasibility
    sub_questions.append("Is this feasible given current constraints (time, budget, technology)?")

    # 5. Risks and downsides
    sub_questions.append("What are the main risks, downsides, or failure modes?")

    # 6. Alternatives
    sub_questions.append("What are the alternative approaches, and how do they compare?")

    # 7. Context-specific questions based on keywords
    lower = idea.lower()
    if any(w in lower for w in ["invest", "buy", "purchase", "cost", "price"]):
        sub_questions.append("What is the expected ROI and total cost of ownership?")
    if any(w in lower for w in ["switch", "migrate", "transition", "replace"]):
        sub_questions.append("What is the migration cost and risk of switching?")
    if any(w in lower for w in ["hire", "team", "employee", "staff"]):
        sub_questions.append("What is the impact on team capacity and culture?")
    if any(w in lower for w in ["research", "paper", "study", "experiment"]):
        sub_questions.append("What is the current state of the art and gap in literature?")
    if any(w in lower for w in ["compare", "versus", "vs", "or"]):
        sub_questions.append("What are the key dimensions for comparison?")

    # 8. Timeline
    sub_questions.append("What is the recommended timeline and next steps?")

    return sub_questions


def build_llm_decompose_prompt(idea_text: str) -> str:
    """Build an LLM prompt for MECE decomposition.

    Returns the user prompt for the LLM to decompose the idea into sub-questions.
    """
    return f"""Decompose the following idea into 5-8 MECE (Mutually Exclusive, Collectively Exhaustive) sub-questions.

Each sub-question should:
1. Cover a distinct aspect (no overlap)
2. Together, they should cover ALL relevant angles
3. Be specific and answerable with evidence
4. Follow the MECE principle

Idea: {idea_text}

Return as a numbered list:
1. ...
2. ...
"""


def parse_decomposition_response(response: str) -> List[str]:
    """Parse an LLM decomposition response into a list of sub-questions."""
    lines = response.strip().split("\n")
    questions = []
    for line in lines:
        # Match numbered list items
        cleaned = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
        if cleaned and len(cleaned) > 10:
            questions.append(cleaned)
    return questions or heuristic_decompose("fallback")

"""MECE decomposition — splits ideas into mutually exclusive, collectively exhaustive sub-questions."""

from __future__ import annotations

from typing import Any, Dict, List


class IdeaDecomposer:
    """Decomposes a rough idea into structured, answerable sub-questions using MECE framework."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def decompose(self, goal_text: str) -> List[Dict[str, Any]]:
        """Decompose a goal into MECE sub-questions.

        TODO: Implement LLM-based decomposition.

        Returns:
            List of sub-question dicts with keys:
            - question: str
            - priority: int
            - evidence_type: str (what kind of evidence is needed)
            - risk: str (what goes wrong if answered incorrectly)
        """
        return []

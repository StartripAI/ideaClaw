"""Evidence gate — verifies sufficient evidence before proceeding.

TODO: Port core logic from OpenRevise scripts/check_revise_sources.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ideaclaw.evidence.extractors import EvidenceCard


@dataclass
class GateResult:
    """Result of evidence gate evaluation."""
    overall_status: str  # PASS | FAIL
    coverage_pct: float
    per_question: List[Dict[str, Any]]
    gaps: List[str]


class EvidenceGate:
    """Evaluates whether sufficient evidence exists to proceed.

    Gate modes:
    - strict: missing required evidence blocks the pipeline
    - lenient: missing evidence produces warnings, pipeline continues
    """

    def __init__(self, config: Dict[str, Any]):
        self.gate_mode = config.get("gate_mode", "strict")

    def evaluate(
        self,
        sub_questions: List[str],
        evidence_cards: List[EvidenceCard],
    ) -> GateResult:
        """Evaluate evidence coverage for each sub-question.

        TODO: Implement gate logic ported from OpenRevise.
        """
        return GateResult(
            overall_status="PASS",
            coverage_pct=0.0,
            per_question=[],
            gaps=[],
        )

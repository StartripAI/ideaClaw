"""Claim-level verification — fact-checks each claim against evidence.

TODO: Port from OpenRevise scripts/check_revision_sop.py
"""

from __future__ import annotations

from typing import Any, Dict, List

from ideaclaw.evidence.extractors import EvidenceCard


class ClaimVerifier:
    """Verifies individual claims against their cited evidence."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def verify(self, evidence_cards: List[EvidenceCard]) -> List[EvidenceCard]:
        """Verify each evidence card and update its verified status.

        TODO: Implement LLM-based verification.
        """
        return evidence_cards

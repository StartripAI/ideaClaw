"""Pipeline stage definitions."""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple, Optional


class Phase(Enum):
    """Pipeline phases."""
    IDEA_SCOPING = "A"
    SOURCE_DISCOVERY = "B"
    EVIDENCE_VERIFICATION = "C"
    SYNTHESIS_DECISION = "D"
    PACK_ASSEMBLY = "E"
    EXPORT_ARCHIVE = "F"


class StageInfo(NamedTuple):
    """Metadata for a pipeline stage."""
    number: int
    name: str
    phase: Phase
    prompt_key: str
    is_gate: bool = False
    rollback_target: Optional[int] = None  # Stage to roll back to on gate failure


class Stage(Enum):
    """All 15 pipeline stages."""

    # Phase A: Idea Scoping
    IDEA_INIT = StageInfo(1, "IDEA_INIT", Phase.IDEA_SCOPING, "idea_init")
    IDEA_DECOMPOSE = StageInfo(2, "IDEA_DECOMPOSE", Phase.IDEA_SCOPING, "idea_decompose")

    # Phase B: Source Discovery
    SEARCH_STRATEGY = StageInfo(3, "SEARCH_STRATEGY", Phase.SOURCE_DISCOVERY, "search_strategy")
    SOURCE_COLLECT = StageInfo(4, "SOURCE_COLLECT", Phase.SOURCE_DISCOVERY, "source_collect")
    SOURCE_SCREEN = StageInfo(5, "SOURCE_SCREEN", Phase.SOURCE_DISCOVERY, "source_screen", is_gate=True)
    EVIDENCE_EXTRACT = StageInfo(6, "EVIDENCE_EXTRACT", Phase.SOURCE_DISCOVERY, "evidence_extract")

    # Phase C: Evidence Verification
    EVIDENCE_GATE = StageInfo(7, "EVIDENCE_GATE", Phase.EVIDENCE_VERIFICATION, "evidence_gate", is_gate=True)
    CLAIM_VERIFY = StageInfo(8, "CLAIM_VERIFY", Phase.EVIDENCE_VERIFICATION, "claim_verify")

    # Phase D: Synthesis & Decision
    EVIDENCE_SYNTHESIS = StageInfo(9, "EVIDENCE_SYNTHESIS", Phase.SYNTHESIS_DECISION, "evidence_synthesis")
    DECISION_TREE = StageInfo(10, "DECISION_TREE", Phase.SYNTHESIS_DECISION, "decision_tree", rollback_target=3)
    COUNTERARGUMENT_GEN = StageInfo(11, "COUNTERARGUMENT_GEN", Phase.SYNTHESIS_DECISION, "counterargument_gen")

    # Phase E: Pack Assembly
    PACK_OUTLINE = StageInfo(12, "PACK_OUTLINE", Phase.PACK_ASSEMBLY, "pack_outline")
    PACK_DRAFT = StageInfo(13, "PACK_DRAFT", Phase.PACK_ASSEMBLY, "pack_draft")
    TRUST_REVIEW = StageInfo(14, "TRUST_REVIEW", Phase.PACK_ASSEMBLY, "trust_review", is_gate=True, rollback_target=13)

    # Phase F: Export & Archive
    EXPORT_PUBLISH = StageInfo(15, "EXPORT_PUBLISH", Phase.EXPORT_ARCHIVE, "export_publish")

    @property
    def info(self) -> StageInfo:
        return self.value


# Ordered list for pipeline execution
STAGE_ORDER: list[Stage] = sorted(Stage, key=lambda s: s.info.number)

GATE_STAGES: list[Stage] = [s for s in STAGE_ORDER if s.info.is_gate]

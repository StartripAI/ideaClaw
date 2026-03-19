"""IdeaClaw Prompt Engine — production-grade prompt library.

Architecture:
  prompts/
  ├── engine.py       — YAML-based prompt loader (legacy PromptEngine)
  ├── system.py       — System-level prompts (personas, constraints, standards)
  ├── generation.py   — Draft generation prompts (16 domains × 3 depths)
  ├── evaluation.py   — Reviewer personas + scoring rubrics (8 personas)
  ├── revision.py     — Targeted revision instructions (per-dimension)
  ├── novelty.py      — Novelty assessment prompts
  ├── evolution.py    — Idea mutation/crossover/evolution prompts
  ├── figure.py       — Figure generation + critique prompts
  ├── library.py      — Prompt library (all constants aggregated)
  └── composer.py     — Dynamic prompt assembler (profile → final prompt)

Usage:
    from ideaclaw.prompts import PromptComposer, PromptLibrary

    composer = PromptComposer()
    prompt = composer.compose_generation(profile, idea, sources, context)
"""

from ideaclaw.prompts.system import (
    PERSONA_RESEARCHER,
    PERSONA_REVIEWER,
    TRUST_CONSTRAINT,
    EVIDENCE_STANDARD,
    FORMAT_RULES,
    ACADEMIC_STANDARD,
)
from ideaclaw.prompts.library import PromptLibrary
from ideaclaw.prompts.composer import PromptComposer

# Legacy engine re-export
try:
    from ideaclaw.prompts.engine import PromptEngine
except ImportError:
    PromptEngine = None

__all__ = [
    "PromptLibrary",
    "PromptComposer",
    "PromptEngine",
    "PERSONA_RESEARCHER",
    "PERSONA_REVIEWER",
    "TRUST_CONSTRAINT",
    "EVIDENCE_STANDARD",
    "FORMAT_RULES",
    "ACADEMIC_STANDARD",
]

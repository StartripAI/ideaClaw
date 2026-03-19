"""PromptLibrary — unified access point for all prompt constants.

Aggregates all prompt modules into a single namespace for easy discovery.
This is the recommended entry point for accessing prompt templates.

Usage:
    from ideaclaw.prompts.library import PromptLibrary as P

logger = logging.getLogger(__name__)

__all__ = ['PromptLibrary']

    # Access domains
    print(P.DOMAINS)           # ['cs_ml', 'cs_systems', ...]
    print(P.PERSONAS)          # ['harsh_reviewer', ...]

    # Get a prompt
    p = P.generation("cs_ml", "deep", idea="attention")
    p = P.review("harsh_reviewer", draft="...")
    p = P.revise(scores={"depth": 0.3}, draft="...")
    p = P.novelty(idea="...", literature="...")
    p = P.mutate(idea="...", mutation_type="pivot")
    p = P.figure(figure_type="bar", title="Results")
"""

from __future__ import annotations
import logging

from typing import Dict, List, Optional

from ideaclaw.prompts.system import (
    PERSONA_RESEARCHER,
    PERSONA_REVIEWER,
    PERSONA_EDITOR,
    PERSONA_STRATEGIST,
    TRUST_CONSTRAINT,
    EVIDENCE_STANDARD,
    ANTI_HALLUCINATION,
    FORMAT_RULES,
    FORMAT_RULES_LATEX,
    ACADEMIC_STANDARD,
    BUSINESS_STANDARD,
    LEGAL_STANDARD,
    MEDICAL_STANDARD,
    DOMAIN_CONTEXT,
)
from ideaclaw.prompts.generation import (
    SECTION_GUIDANCE,
    DEPTH_CONFIGS,
    get_generation_prompt,
    get_domains,
    get_section_guidance,
)
from ideaclaw.prompts.evaluation import (
    PERSONAS as REVIEWER_PERSONAS,
    get_reviewer_prompt,
    get_multi_review_prompt,
    get_persona_names,
)
from ideaclaw.prompts.revision import (
    REVISION_INSTRUCTIONS,
    get_revision_prompt,
    get_revision_dimensions,
)
from ideaclaw.prompts.novelty import (
    get_novelty_prompt,
    get_gap_prompt,
)
from ideaclaw.prompts.evolution import (
    MUTATION_TYPES,
    get_mutation_prompt,
    get_crossover_prompt,
    get_mutation_types,
)
from ideaclaw.prompts.figure import (
    FIGURE_TYPES,
    get_figure_codegen_prompt,
    get_figure_critique_prompt,
    get_caption_prompt,
)


class PromptLibrary:
    """Unified access to all IdeaClaw prompt templates.

    Static class — all methods are classmethods for convenience.

    Counts:
      - 16 domain templates
      - 8 reviewer personas
      - 10 revision dimensions
      - 7 mutation types
      - 13 figure types
      - 3 depth levels
      - 4 writing standards
      - 4 persona types
    """

    # --- Constants ---
    DOMAINS = get_domains()
    PERSONAS = get_persona_names()
    REVISION_DIMS = get_revision_dimensions()
    MUTATION_TYPES = get_mutation_types()
    FIGURE_TYPES = list(FIGURE_TYPES.keys())
    DEPTH_LEVELS = list(DEPTH_CONFIGS.keys())

    # --- System prompts ---
    SYSTEM_RESEARCHER = PERSONA_RESEARCHER
    SYSTEM_REVIEWER = PERSONA_REVIEWER
    SYSTEM_EDITOR = PERSONA_EDITOR
    SYSTEM_STRATEGIST = PERSONA_STRATEGIST
    TRUST = TRUST_CONSTRAINT
    EVIDENCE = EVIDENCE_STANDARD
    ANTI_HALLUCINATION = ANTI_HALLUCINATION
    FORMAT_MD = FORMAT_RULES
    FORMAT_LATEX = FORMAT_RULES_LATEX
    ACADEMIC = ACADEMIC_STANDARD
    BUSINESS = BUSINESS_STANDARD
    LEGAL = LEGAL_STANDARD
    MEDICAL = MEDICAL_STANDARD

    @classmethod
    def generation(cls, domain: str = "general", depth: str = "standard", **kwargs) -> dict:
        """Get a generation prompt for a domain and depth."""
        return get_generation_prompt(domain, depth, **kwargs)

    @classmethod
    def review(cls, persona: str = "harsh_reviewer", draft: str = "", profile=None) -> dict:
        """Get a review prompt for a persona."""
        return get_reviewer_prompt(persona, draft, profile)

    @classmethod
    def multi_review(cls, draft: str, n: int = 3) -> dict:
        """Get a multi-perspective review prompt."""
        return get_multi_review_prompt(draft, n)

    @classmethod
    def revise(cls, scores: Dict[str, float] = None, draft: str = "", **kwargs) -> dict:
        """Get a revision prompt based on evaluation scores."""
        return get_revision_prompt(scores or {}, draft, **kwargs)

    @classmethod
    def novelty(cls, idea: str, literature: str = "") -> dict:
        """Get a novelty assessment prompt."""
        return get_novelty_prompt(idea, literature)

    @classmethod
    def gap(cls, papers: str, domain: str = "general") -> dict:
        """Get a research gap identification prompt."""
        return get_gap_prompt(papers, domain)

    @classmethod
    def mutate(cls, idea: str, mutation_type: str = "expand", **kwargs) -> dict:
        """Get a mutation prompt."""
        return get_mutation_prompt(idea, mutation_type, **kwargs)

    @classmethod
    def crossover(cls, idea_a: str, idea_b: str, **kwargs) -> dict:
        """Get a crossover prompt."""
        return get_crossover_prompt(idea_a, idea_b, **kwargs)

    @classmethod
    def figure(cls, figure_type: str = "bar", **kwargs) -> dict:
        """Get a figure codegen prompt."""
        return get_figure_codegen_prompt(figure_type, **kwargs)

    @classmethod
    def figure_critique(cls, description: str, code: str, venue: str = "NeurIPS") -> dict:
        """Get a figure critique prompt."""
        return get_figure_critique_prompt(description, code, venue)

    @classmethod
    def caption(cls, figure_type: str, title: str, description: str, **kwargs) -> dict:
        """Get a caption generation prompt."""
        return get_caption_prompt(figure_type, title, description, **kwargs)

    @classmethod
    def domain_context(cls, domain: str) -> str:
        """Get domain-specific context string."""
        return DOMAIN_CONTEXT.get(domain, DOMAIN_CONTEXT["general"])

    @classmethod
    def section_guidance(cls, domain: str) -> dict:
        """Get section guidance for a domain."""
        return get_section_guidance(domain)

    @classmethod
    def reviewer_persona(cls, key: str) -> dict:
        """Get a reviewer persona definition."""
        return REVIEWER_PERSONAS.get(key, REVIEWER_PERSONAS["harsh_reviewer"])

    @classmethod
    def revision_instruction(cls, dimension: str) -> dict:
        """Get revision instructions for a specific dimension."""
        return REVISION_INSTRUCTIONS.get(dimension, {})

    @classmethod
    def stats(cls) -> dict:
        """Get statistics about the prompt library."""
        return {
            "domains": len(cls.DOMAINS),
            "personas": len(cls.PERSONAS),
            "revision_dimensions": len(cls.REVISION_DIMS),
            "mutation_types": len(cls.MUTATION_TYPES),
            "figure_types": len(cls.FIGURE_TYPES),
            "depth_levels": len(cls.DEPTH_LEVELS),
            "total_templates": (
                len(cls.DOMAINS) * len(cls.DEPTH_LEVELS) +  # generation
                len(cls.PERSONAS) +                          # evaluation
                len(cls.REVISION_DIMS) * 2 +                 # revision (mild+severe)
                len(cls.MUTATION_TYPES) +                     # evolution
                len(cls.FIGURE_TYPES) +                       # figure
                4                                             # novelty + gap + crossover + multi_review
            ),
        }

"""PromptComposer — dynamic prompt assembly from profile + context.

Given a ScenarioProfile, personalized context, and run state,
composes the optimal prompt by selecting and combining templates.

This is the recommended way to generate prompts in the ResearchLoop.

Usage:
    composer = PromptComposer()
    prompt = composer.compose_generation(profile, idea, sources)
    prompt = composer.compose_evaluation(profile, draft, sources)
    prompt = composer.compose_revision(profile, draft, scores)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ideaclaw.prompts.system import (
    PERSONA_RESEARCHER,
    PERSONA_REVIEWER,
    TRUST_CONSTRAINT,
    EVIDENCE_STANDARD,
    ANTI_HALLUCINATION,
    FORMAT_RULES,
    FORMAT_RULES_LATEX,
    DOMAIN_CONTEXT,
)
from ideaclaw.prompts.generation import get_generation_prompt, SECTION_GUIDANCE
from ideaclaw.prompts.evaluation import get_reviewer_prompt, get_multi_review_prompt, PERSONAS
from ideaclaw.prompts.revision import get_revision_prompt

if TYPE_CHECKING:
    from ideaclaw.orchestrator.loop import ScenarioProfile

logger = logging.getLogger(__name__)

__all__ = ["PromptComposer"]


class PromptComposer:
    """Dynamic prompt assembler that adapts to profile and context.

    Composes prompts by:
    1. Selecting the right domain template
    2. Injecting personalized context (style, memory, skills)
    3. Choosing depth based on iteration and score
    4. Adding trust constraints and evidence standards
    5. Formatting for the output type (markdown or LaTeX)
    """

    def __init__(
        self,
        default_depth: str = "standard",
        reviewer_personas: Optional[List[str]] = None,
        include_anti_hallucination: bool = True,
        output_format: str = "markdown",
    ):
        self.default_depth = default_depth
        self.reviewer_personas = reviewer_personas or ["harsh_reviewer", "methodology_expert", "clarity_editor"]
        self.include_anti_hallucination = include_anti_hallucination
        self.output_format = output_format

    def compose_generation(
        self,
        profile: "ScenarioProfile",
        idea: str,
        sources: str = "",
        previous_draft: str = "",
        feedback: str = "",
        personalized_context: str = "",
        iteration: int = 0,
        current_score: float = 0.0,
        weak_dimensions: str = "",
    ) -> dict:
        """Compose a generation prompt adapted to the profile and run state.

        Automatically selects depth based on iteration and score:
        - Iteration 0: standard depth (establish the foundation)
        - Low score + later iteration: deep depth (need more substance)
        - High score + later iteration: quick depth (targeted fixes only)
        """
        # Auto-select depth
        if iteration == 0:
            depth = self.default_depth
        elif current_score < 0.5 and iteration >= 2:
            depth = "deep"
        elif current_score > 0.7 and iteration >= 2:
            depth = "quick"
        else:
            depth = self.default_depth

        # Extract domain from profile
        domain = self._extract_domain(profile)

        # Build format rules
        format_rules = FORMAT_RULES_LATEX if self.output_format == "latex" else FORMAT_RULES

        # Add anti-hallucination if enabled
        extra_context = ""
        if self.include_anti_hallucination:
            extra_context += f"\n{ANTI_HALLUCINATION}\n"
        if personalized_context:
            extra_context += f"\n{personalized_context}\n"
        extra_context += f"\n{format_rules}\n"

        # Get base prompt
        prompt = get_generation_prompt(
            domain=domain,
            depth=depth,
            idea=idea,
            sources=sources,
            previous_draft=previous_draft,
            feedback=feedback,
            weak_dimensions=weak_dimensions,
            personalized_context=extra_context,
        )

        # Inject profile-specific overrides
        if hasattr(profile, "style") and profile.style:
            style_note = self._build_style_note(profile)
            prompt["user"] = f"{style_note}\n\n{prompt['user']}"

        return prompt

    def compose_evaluation(
        self,
        profile: "ScenarioProfile",
        draft: str,
        sources: list = None,
        multi_perspective: bool = False,
    ) -> dict:
        """Compose an evaluation prompt.

        Uses multi-perspective review for first evaluation,
        single persona for subsequent iterations.
        """
        if multi_perspective:
            return get_multi_review_prompt(draft, len(self.reviewer_personas))

        # Select the most appropriate persona based on profile
        domain = self._extract_domain(profile)
        if domain in ("medical", "bio", "chemistry"):
            persona = "methodology_expert"
        elif domain in ("math", "physics"):
            persona = "statistical_reviewer"
        elif domain in ("legal", "humanities"):
            persona = "clarity_editor"
        else:
            persona = self.reviewer_personas[0] if self.reviewer_personas else "harsh_reviewer"

        return get_reviewer_prompt(persona, draft, profile)

    def compose_revision(
        self,
        profile: "ScenarioProfile",
        draft: str,
        scores: Dict[str, float],
        custom_feedback: str = "",
    ) -> dict:
        """Compose a revision prompt targeting the weakest dimensions."""
        return get_revision_prompt(
            scores=scores,
            draft=draft,
            profile=profile,
            custom_feedback=custom_feedback,
        )

    def compose_novelty_check(self, idea: str, literature: str = "") -> dict:
        """Compose a novelty assessment prompt."""
        from ideaclaw.prompts.novelty import get_novelty_prompt
        return get_novelty_prompt(idea, literature)

    def compose_mutation(
        self,
        idea: str,
        mutation_type: str = "expand",
        domain: str = "general",
        n_variants: int = 3,
    ) -> dict:
        """Compose an idea mutation prompt."""
        from ideaclaw.prompts.evolution import get_mutation_prompt
        return get_mutation_prompt(idea, mutation_type, domain, n_variants)

    # --- Internal helpers ---

    def _extract_domain(self, profile: "ScenarioProfile") -> str:
        """Extract domain key from profile."""
        if hasattr(profile, "category"):
            cat = profile.category.lower().replace(" ", "_")
            if cat in DOMAIN_CONTEXT:
                return cat
            # Fuzzy match
            for key in DOMAIN_CONTEXT:
                if key in cat or cat in key:
                    return key
        return "general"

    def _build_style_note(self, profile: "ScenarioProfile") -> str:
        """Build style constraint note from profile."""
        parts = []
        style = profile.style
        if hasattr(style, "required_sections") and style.required_sections:
            parts.append(f"REQUIRED SECTIONS: {', '.join(style.required_sections)}")
        if hasattr(style, "max_words") and style.max_words:
            parts.append(f"MAX LENGTH: {style.max_words} words")
        if hasattr(style, "min_words") and style.min_words:
            parts.append(f"MIN LENGTH: {style.min_words} words")
        if hasattr(style, "tone") and style.tone:
            parts.append(f"TONE: {style.tone}")
        if hasattr(style, "citation_style") and style.citation_style:
            parts.append(f"CITATION STYLE: {style.citation_style}")
        return "\n".join(parts)

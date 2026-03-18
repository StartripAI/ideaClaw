"""Default LLM-powered hooks for the orchestrator loop.

Wires existing LLMClient (BYOK, 6 providers, fallback chain) into the
orchestrator's hook protocols. This is the "brain" — turns the empty pipe
into a real content-generation system.

Usage:
    from ideaclaw.config import load_config
    from ideaclaw.orchestrator.hooks import LLMHooks

    hooks = LLMHooks(load_config())
    # Now pass hooks.generate, hooks.evaluate, etc. to ResearchLoop
    # Or just: ResearchLoop(config=load_config())  # auto-wires

AR pattern integration:
    - profile YAML → system prompt (like program.md)
    - Optional program.md override → user-editable objective
    - train.md → auto-generated experiment log (like AR's train.md)
"""

from __future__ import annotations

import json
import logging
import textwrap
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ideaclaw.orchestrator.evaluator import UnifiedEvaluator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_generate_prompt(
    profile: Any,
    sources: List[Any],
    previous_draft: Optional[str],
    feedback: str,
    program_md: str = "",
) -> tuple[str, str]:
    """Build system + user prompts from profile + sources.

    Returns (system_prompt, user_prompt) tuple.
    """
    # Objective: program.md overrides YAML if present
    objective = program_md.strip() if program_md else profile.objective

    # Required sections as numbered list
    sections_list = ""
    if hasattr(profile, "style") and profile.style.required_sections:
        sections_list = "\n".join(
            f"  {i+1}. {s.title()}"
            for i, s in enumerate(profile.style.required_sections)
        )

    # Format sources as reference list
    sources_text = ""
    if sources:
        refs = []
        for i, src in enumerate(sources[:20], 1):  # Cap at 20
            if isinstance(src, dict):
                title = src.get("title", "Untitled")
                year = src.get("year", "")
                abstract = src.get("abstract", "")[:200]
                refs.append(f"[{i}] {title} ({year})\n    {abstract}")
            else:
                refs.append(f"[{i}] {src}")
        sources_text = "\n".join(refs)

    # Style instructions
    formality = getattr(profile.style, "formality", 0.8) if hasattr(profile, "style") else 0.8
    voice = getattr(profile.style, "voice", "third_person") if hasattr(profile, "style") else "third_person"
    cite_style = getattr(profile.style, "citation_style", "natbib") if hasattr(profile, "style") else "natbib"

    tone_map = {
        (0.0, 0.3): "casual, conversational",
        (0.3, 0.6): "professional but approachable",
        (0.6, 0.8): "formal, professional",
        (0.8, 1.01): "highly formal, academic",
    }
    tone = "professional"
    for (lo, hi), desc in tone_map.items():
        if lo <= formality < hi:
            tone = desc
            break

    voice_map = {
        "first_person": "first person (I/we)",
        "third_person": "third person (the authors, this paper)",
        "second_person": "second person (you)",
        "mixed": "mixed voice as appropriate",
    }
    voice_desc = voice_map.get(voice, voice)

    system_prompt = textwrap.dedent(f"""\
        You are an expert writer producing a {profile.display_name}.

        OBJECTIVE:
        {objective}

        STRUCTURE (required sections):
        {sections_list or "Use appropriate sections for this document type."}

        STYLE:
        - Tone: {tone}
        - Voice: {voice_desc}
        - Citation style: {cite_style}
        - Category: {profile.category}

        RULES:
        - Write the COMPLETE document, not an outline or summary.
        - Include real citations referencing the provided sources.
        - Be specific, detailed, and substantive.
        - Match the quality expected for {profile.display_name}.
    """)

    # User prompt
    parts = []
    if sources_text:
        parts.append(f"REFERENCE SOURCES:\n{sources_text}")

    if previous_draft and feedback:
        parts.append(f"PREVIOUS DRAFT (improve based on feedback):\n{previous_draft[:3000]}")
        parts.append(f"FEEDBACK TO ADDRESS:\n{feedback}")
    elif previous_draft:
        parts.append(f"PREVIOUS DRAFT (improve it):\n{previous_draft[:3000]}")
    else:
        parts.append("Write the complete document now.")

    user_prompt = "\n\n".join(parts)

    return system_prompt, user_prompt


def build_judge_prompt(
    profile: Any,
    draft: str,
    criteria_names: List[str],
) -> tuple[str, str]:
    """Build LLM-as-judge prompt for subjective evaluation dimensions.

    Returns (system_prompt, user_prompt).
    """
    criteria_desc = "\n".join(f"- {name}: score 0.0-1.0" for name in criteria_names)

    system_prompt = textwrap.dedent(f"""\
        You are a strict reviewer for {profile.display_name}.
        Evaluate the following document on these criteria:
        {criteria_desc}

        Return ONLY a JSON object with criterion names as keys and float scores (0.0-1.0) as values.
        Be critical and realistic. Score relative to the standards of {profile.display_name}.
        Example response: {{"novelty": 0.65, "significance": 0.72}}
    """)

    user_prompt = f"DOCUMENT TO EVALUATE:\n\n{draft[:6000]}"

    return system_prompt, user_prompt


def build_feedback_prompt(
    profile: Any,
    scores: Dict[str, float],
    criteria: List[Any],
) -> str:
    """Build actionable feedback from scores for the next iteration."""
    weak = []
    for c in criteria:
        score = scores.get(c.name, 0)
        if score < c.min_score:
            weak.append(f"- {c.name}: {score:.2f} (needs ≥{c.min_score:.2f})")
        elif score < 0.7:
            weak.append(f"- {c.name}: {score:.2f} (could improve)")

    if not weak:
        return "All criteria met. Polish and refine."

    return "Focus on improving these weak areas:\n" + "\n".join(weak)


# ---------------------------------------------------------------------------
# LLMHooks — default implementations
# ---------------------------------------------------------------------------

class LLMHooks:
    """Default LLM-powered hook implementations for the orchestrator loop.

    Wires existing LLMClient (from llm/client.py) into the loop's
    generate, evaluate, and learn hooks. Supports optional program.md
    override (AR-style user-editable experiment specification).

    Usage:
        hooks = LLMHooks(load_config())
        loop = ResearchLoop(
            generate_fn=hooks.generate,
            evaluate_fn=hooks.evaluate,
            learn_fn=hooks.learn,
        )
    """

    def __init__(self, config: Any, program_md_path: Optional[Path] = None):
        """Initialize with config (dict or IdeaClawConfig).

        Args:
            config: Configuration (dict with 'llm' key, or IdeaClawConfig).
            program_md_path: Optional path to program.md override file.
        """
        from ideaclaw.llm.client import LLMClient

        # Handle both dict and IdeaClawConfig
        if hasattr(config, "llm"):
            llm_cfg = asdict(config.llm) if hasattr(config.llm, "__dataclass_fields__") else config.llm
        elif isinstance(config, dict):
            llm_cfg = config.get("llm", {})
        else:
            llm_cfg = {}

        self.llm = LLMClient(llm_cfg)
        self._heuristic_evaluator = UnifiedEvaluator()
        self._program_md = ""

        # Load program.md if it exists
        if program_md_path and program_md_path.exists():
            self._program_md = program_md_path.read_text(encoding="utf-8")
            logger.info("Loaded program.md override from %s", program_md_path)

        # Also check CWD for program.md (AR convention)
        cwd_program = Path("program.md")
        if not self._program_md and cwd_program.exists():
            self._program_md = cwd_program.read_text(encoding="utf-8")
            logger.info("Loaded program.md from current directory")

        # LLM-judged dimensions (subjective, can't be heuristic)
        self._llm_judge_dims = {"novelty", "significance", "soundness", "ethics"}

    def search(self, profile: Any, context: Dict[str, Any]) -> List[Any]:
        """Search for sources using the source module.

        Falls back to empty list if source module unavailable.
        """
        try:
            from ideaclaw.source.collector import collect_sources
            query = profile.objective or profile.display_name
            results = collect_sources(
                query=query,
                engines=profile.search.apis,
                limit=profile.search.max_sources,
            )
            logger.info("Found %d sources for '%s'", len(results), query[:50])
            return results
        except ImportError:
            logger.warning("Source module not available, using empty sources")
            return []
        except Exception as e:
            logger.warning("Search failed: %s", e)
            return []

    def generate(
        self,
        profile: Any,
        sources: List[Any],
        previous_draft: Optional[str],
        feedback: str,
    ) -> str:
        """Generate document content using LLM.

        Builds prompt from profile YAML (or program.md override) + sources,
        then calls LLMClient.chat_with_fallback().
        """
        system_prompt, user_prompt = build_generate_prompt(
            profile, sources, previous_draft, feedback,
            program_md=self._program_md,
        )

        logger.info("Generating %s (iter feedback: %s)",
                     profile.display_name, feedback[:50] if feedback else "initial")

        content = self.llm.chat_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=4096,
        )

        logger.info("Generated %d chars", len(content))
        return content

    def evaluate(
        self,
        profile: Any,
        draft: str,
        sources: List[Any],
    ) -> Dict[str, float]:
        """Hybrid evaluation: heuristic + LLM-as-judge.

        - Heuristic dimensions (structure, citations, depth, clarity, style,
          formatting): computed locally by UnifiedEvaluator.
        - LLM-judged dimensions (novelty, significance, soundness, ethics):
          scored by LLM-as-judge prompt.

        Returns {dimension_name: score} dict.
        """
        # 1. Heuristic scores (free, fast)
        scores = self._heuristic_evaluator.evaluate(profile, draft, sources)

        # 2. LLM-judge for subjective dimensions
        criteria_names = [c.name for c in profile.criteria]
        llm_dims = [n for n in criteria_names if n in self._llm_judge_dims]

        if llm_dims:
            try:
                sys_prompt, user_prompt = build_judge_prompt(
                    profile, draft, llm_dims,
                )
                raw = self.llm.chat_with_fallback(
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                    json_mode=True,
                    temperature=0.1,
                    max_tokens=256,
                )

                # Parse JSON response
                llm_scores = json.loads(raw)
                for dim in llm_dims:
                    if dim in llm_scores:
                        val = float(llm_scores[dim])
                        scores[dim] = max(0.0, min(1.0, val))
                        logger.debug("LLM judge %s = %.2f", dim, scores[dim])
            except Exception as e:
                logger.warning("LLM judge failed, keeping heuristic: %s", e)

        return scores

    def learn(
        self,
        profile: Any,
        draft: str,
        scores: Dict[str, float],
        failure_reason: str,
    ) -> None:
        """Update train.md experiment log (AR pattern).

        Records what worked, what didn't, and suggestions for next iteration.
        """
        train_md = Path("train.md")
        entry = (
            f"\n## Iteration — {profile.display_name}\n"
            f"Scores: {', '.join(f'{k}={v:.2f}' for k, v in sorted(scores.items()))}\n"
        )
        if failure_reason:
            entry += f"Failed: {failure_reason}\n"
        entry += f"Draft length: {len(draft)} chars\n"

        try:
            existing = train_md.read_text(encoding="utf-8") if train_md.exists() else "# IdeaClaw Experiment Log\n"
            train_md.write_text(existing + entry, encoding="utf-8")
        except OSError:
            pass  # Non-critical


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_hooks(config: Any, program_md: Optional[Path] = None) -> LLMHooks:
    """Create LLMHooks from config. Convenience factory."""
    return LLMHooks(config, program_md_path=program_md)

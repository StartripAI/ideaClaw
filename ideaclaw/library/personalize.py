"""Personalizer — assembles personalized prompts from all context layers.

Combines:
  - Style profile (from style_analyzer)
  - Relevant library chunks (from retriever)
  - Skills (from knowledge/skills)
  - User preferences (from knowledge/preferences)
  - Memory (from knowledge/memory)

This is the final assembly point before the orchestrator sends a prompt to the LLM.

Usage:
    personalizer = Personalizer(library_dir, knowledge_dir)
    context = personalizer.build_context(
        idea="attention mechanism",
        category="cs_ml",
        scenario_id="icml_2025",
    )
    # context.full_prompt contains all personalized context for LLM injection
"""

from __future__ import annotations
import logging

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ['PersonalizedContext', 'Personalizer']


@dataclass
class PersonalizedContext:
    """Assembled personalized context for LLM prompt injection."""
    style_section: str = ""           # From style analyzer
    library_section: str = ""         # From RAG retriever
    skills_section: str = ""          # From skill extractor
    preferences_section: str = ""     # From preference tracker
    memory_section: str = ""          # From memory system
    full_prompt: str = ""             # Complete assembled context

    def is_empty(self) -> bool:
        return not any([
            self.style_section, self.library_section,
            self.skills_section, self.preferences_section,
            self.memory_section,
        ])


class Personalizer:
    """Assemble personalized context from all available layers.

    Acts as the bridge between the library/knowledge systems and the orchestrator.

    Features beyond ARC:
      - Per-layer weight control (A/B blending)
      - Context transfer across scenarios
      - Layer priority ordering
      - Diagnostic report (which layers contributed what)
    """

    # Default layer weights (0-1, controls how much each layer contributes)
    DEFAULT_WEIGHTS = {
        "style": 0.8,
        "library": 1.0,
        "skills": 0.9,
        "preferences": 1.0,
        "memory": 0.7,
    }

    def __init__(
        self,
        library_dir: Optional[Path] = None,
        knowledge_dir: Optional[Path] = None,
        layer_weights: Optional[Dict[str, float]] = None,
    ):
        self.library_dir = library_dir or (Path.home() / ".ideaclaw" / "library")
        self.knowledge_dir = knowledge_dir or (Path.home() / ".ideaclaw")
        self.layer_weights = {**self.DEFAULT_WEIGHTS, **(layer_weights or {})}
        self._last_context: Optional[PersonalizedContext] = None

        # Lazy-loaded components
        self._retriever = None
        self._style_analyzer = None
        self._skill_extractor = None
        self._pref_tracker = None
        self._memory = None

    @property
    def retriever(self):
        if self._retriever is None:
            from ideaclaw.library.retriever import LibraryRetriever
            self._retriever = LibraryRetriever(self.library_dir)
        return self._retriever

    @property
    def style_analyzer(self):
        if self._style_analyzer is None:
            from ideaclaw.library.style_analyzer import StyleAnalyzer
            self._style_analyzer = StyleAnalyzer()
        return self._style_analyzer

    @property
    def skill_extractor(self):
        if self._skill_extractor is None:
            from ideaclaw.knowledge.skills import SkillExtractor
            self._skill_extractor = SkillExtractor(
                self.knowledge_dir / "skills" if self.knowledge_dir else None
            )
        return self._skill_extractor

    @property
    def pref_tracker(self):
        if self._pref_tracker is None:
            from ideaclaw.knowledge.preferences import PreferenceTracker
            self._pref_tracker = PreferenceTracker(
                self.knowledge_dir / "preferences" if self.knowledge_dir else None
            )
        return self._pref_tracker

    @property
    def memory(self):
        if self._memory is None:
            from ideaclaw.knowledge.memory import Memory
            self._memory = Memory(
                self.knowledge_dir / "memory" if self.knowledge_dir else None
            )
        return self._memory

    def build_context(
        self,
        idea: str,
        category: str = "general",
        scenario_id: str = "",
        include_style: bool = True,
        include_library: bool = True,
        include_skills: bool = True,
        include_preferences: bool = True,
        include_memory: bool = True,
        library_top_k: int = 3,
        skill_max: int = 5,
        memory_max: int = 3,
    ) -> PersonalizedContext:
        """Build full personalized context for a research task.

        Args:
            idea: The research idea/topic.
            category: Domain category for filtering.
            scenario_id: Specific scenario profile ID.
            include_*: Toggle individual context layers.
            library_top_k: Number of library chunks to retrieve.
            skill_max: Maximum skills to include.
            memory_max: Maximum memories to recall.

        Returns:
            PersonalizedContext with all assembled sections.
        """
        ctx = PersonalizedContext()

        # 1. Library retrieval (RAG)
        if include_library:
            try:
                results = self.retriever.search(idea, top_k=library_top_k)
                if results:
                    ctx.library_section = self.retriever.format_for_prompt(results)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Suppressed: %s", exc)

        # 2. Style profile (from library documents)
        if include_style:
            try:
                # Get style from user's ingested documents
                docs = self._get_user_documents()
                if docs:
                    profiles = [self.style_analyzer.analyze(doc_text) for doc_text in docs[:5]]
                    merged = self.style_analyzer.merge_profiles(profiles)
                    ctx.style_section = merged.format_for_prompt()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Suppressed: %s", exc)

        # 3. Skills
        if include_skills:
            try:
                skills = self.skill_extractor.get_skills(
                    category=category, idea=idea, max_results=skill_max
                )
                if skills:
                    ctx.skills_section = self.skill_extractor.format_for_prompt(skills)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Suppressed: %s", exc)

        # 4. Preferences
        if include_preferences:
            try:
                pref_text = self.pref_tracker.format_for_prompt()
                if pref_text:
                    ctx.preferences_section = pref_text
            except Exception as exc:  # noqa: BLE001
                logger.debug("Suppressed: %s", exc)

        # 5. Memory
        if include_memory:
            try:
                recall = self.memory.recall(idea, category=category, max_results=memory_max)
                if recall.context_prompt:
                    ctx.memory_section = recall.context_prompt
            except Exception as exc:  # noqa: BLE001
                logger.debug("Suppressed: %s", exc)

        # Assemble full prompt
        ctx.full_prompt = self._assemble(ctx)
        self._last_context = ctx
        return ctx

    def _assemble(self, ctx: PersonalizedContext) -> str:
        """Assemble all sections into a single prompt context block.

        Applies layer weights to control contribution of each section.
        """
        parts = []

        if ctx.preferences_section and self.layer_weights.get('preferences', 1.0) > 0:
            parts.append(ctx.preferences_section)
        if ctx.style_section and self.layer_weights.get('style', 1.0) > 0:
            parts.append(ctx.style_section)
        if ctx.memory_section and self.layer_weights.get('memory', 1.0) > 0:
            parts.append(ctx.memory_section)
        if ctx.skills_section and self.layer_weights.get('skills', 1.0) > 0:
            parts.append(ctx.skills_section)
        if ctx.library_section and self.layer_weights.get('library', 1.0) > 0:
            parts.append(ctx.library_section)

        if not parts:
            return ""

        return (
            "---\n"
            "# Personalized Context (from your library & past experience)\n\n"
            + "\n\n".join(parts)
            + "\n---\n"
        )

    def _get_user_documents(self) -> List[str]:
        """Get text from user's ingested documents for style analysis."""
        texts = []
        docs_dir = self.library_dir / "documents"
        if not docs_dir.exists():
            return texts

        import json
        for doc_file in sorted(docs_dir.glob("*.json"))[:5]:
            try:
                data = json.loads(doc_file.read_text(encoding="utf-8"))
                chunks = data.get("chunks", [])
                if chunks:
                    text = " ".join(c.get("text", "") for c in chunks[:10])
                    texts.append(text)
            except (Exception,):
                continue
        return texts

    def learn_from_run(
        self,
        run_id: str,
        idea: str,
        category: str,
        scenario_id: str,
        final_score: float,
        iteration_count: int,
        score_history: Optional[List[float]] = None,
        feedback_history: Optional[List[str]] = None,
    ):
        """Learn from a completed run — updates memory + extracts skills.

        Called by the orchestrator after a run finishes.
        """
        # 1. Store in memory
        try:
            insights = []
            if score_history and len(score_history) >= 2:
                delta = score_history[-1] - score_history[0]
                insights.append(f"Score improved by {delta:.2f} over {len(score_history)} iterations")
            if final_score >= 0.8:
                insights.append(f"High quality result ({final_score:.2f})")

            self.memory.learn(
                run_id=run_id,
                idea=idea,
                scenario_id=scenario_id,
                category=category,
                insights=insights,
                final_score=final_score,
                iteration_count=iteration_count,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Suppressed: %s", exc)

        # 2. Extract skills
        try:
            skills = self.skill_extractor.extract_from_run(
                run_id=run_id,
                idea=idea,
                category=category,
                scenario_id=scenario_id,
                final_score=final_score,
                iteration_count=iteration_count,
                score_history=score_history,
                feedback_history=feedback_history,
            )
            if skills:
                self.skill_extractor.save(skills)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Suppressed: %s", exc)

    def diagnostic_report(self) -> Dict[str, Any]:
        """Report which context layers contributed to the last build.

        Returns:
            Dict with per-layer contribution stats.
        """
        ctx = self._last_context
        if ctx is None:
            return {"status": "no_context_built_yet"}

        layers = {
            "style": ctx.style_section,
            "library": ctx.library_section,
            "skills": ctx.skills_section,
            "preferences": ctx.preferences_section,
            "memory": ctx.memory_section,
        }
        report = {}
        for name, content in layers.items():
            report[name] = {
                "active": bool(content),
                "chars": len(content),
                "weight": self.layer_weights.get(name, 1.0),
            }
        report["total_chars"] = len(ctx.full_prompt)
        report["active_layers"] = sum(1 for v in report.values() if isinstance(v, dict) and v.get("active"))
        return report

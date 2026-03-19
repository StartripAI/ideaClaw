"""Skill extraction from research run outcomes.

Automatically extracts reusable skills from successful and failed runs.
Like ARC's lesson→skill pipeline, but with dedup + heuristic dual-mode:
  - Statistical mode: pattern extraction from structured run data
  - LLM mode: LLM-generated skill descriptions from run context

Usage:
    extractor = SkillExtractor()
    skills = extractor.extract_from_run(run_state)
    extractor.save(skills)

    # Later, retrieve skills for a new run
    relevant = extractor.get_skills(category="cs_ml", idea="attention")
"""

from __future__ import annotations
import logging

import hashlib
import json
import re
import datetime as dt
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ['Skill', 'SkillExtractor']


@dataclass
class Skill:
    """A reusable skill extracted from research experience."""
    id: str
    name: str
    description: str
    category: str                     # Domain category
    source_type: str                  # "success" or "failure"
    trigger: str                      # When to apply this skill
    action: str                       # What to do
    evidence: str                     # Why this works (from the run)
    strength: float = 1.0             # Confidence / frequency
    usage_count: int = 0
    created_at: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Skill":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class SkillExtractor:
    """Extract and manage reusable skills from research runs.

    Stores at: ~/.ideaclaw/skills/
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or (Path.home() / ".ideaclaw" / "skills")
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = self.skills_dir / "skills.json"
        self._skills: List[Skill] = []
        self._load()

    # ---- Extraction (Heuristic Mode) ----

    def extract_from_run(
        self,
        run_id: str,
        idea: str,
        category: str,
        scenario_id: str,
        final_score: float,
        iteration_count: int,
        score_history: Optional[List[float]] = None,
        feedback_history: Optional[List[str]] = None,
        sources_used: Optional[List[Dict]] = None,
    ) -> List[Skill]:
        """Extract skills from a completed run using heuristic patterns.

        Analyzes:
        - Score trajectory (improvement patterns)
        - Feedback patterns (recurring themes)
        - Source effectiveness
        - Iteration efficiency

        Returns:
            List of extracted Skill objects.
        """
        extracted: List[Skill] = []
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        scores = score_history or []
        feedbacks = feedback_history or []

        # 1. Score trajectory skills
        if len(scores) >= 2:
            # Big improvement pattern
            max_jump = max(scores[i] - scores[i - 1] for i in range(1, len(scores)))
            if max_jump > 0.15:
                jump_idx = next(i for i in range(1, len(scores)) if scores[i] - scores[i-1] == max_jump)
                feedback_at_jump = feedbacks[jump_idx] if jump_idx < len(feedbacks) else ""
                extracted.append(Skill(
                    id=self._make_id(f"{run_id}:score_jump"),
                    name=f"Score Jump Pattern ({category})",
                    description=f"Large score improvement (+{max_jump:.2f}) at iteration {jump_idx + 1}",
                    category=category,
                    source_type="success",
                    trigger=f"Score plateaus in {category} domain",
                    action=f"Apply revision strategy from iteration {jump_idx + 1}: {feedback_at_jump[:200]}",
                    evidence=f"Score jumped from {scores[jump_idx-1]:.2f} to {scores[jump_idx]:.2f}",
                    created_at=now,
                    tags=[category, "score-improvement"],
                ))

            # Diminishing returns pattern
            if len(scores) >= 4:
                late_gains = [scores[i] - scores[i-1] for i in range(len(scores)//2, len(scores))]
                if all(g < 0.02 for g in late_gains):
                    extracted.append(Skill(
                        id=self._make_id(f"{run_id}:dim_returns"),
                        name=f"Diminishing Returns ({category})",
                        description="Later iterations show minimal improvement",
                        category=category,
                        source_type="failure",
                        trigger=f"Score gain < 0.02 for 2+ iterations in {category}",
                        action="Stop iterating early; focus on structural changes or switch approach",
                        evidence=f"Final {len(late_gains)} gains: {[f'{g:.3f}' for g in late_gains]}",
                        created_at=now,
                        tags=[category, "iteration-policy"],
                    ))

        # 2. Feedback pattern skills
        if feedbacks:
            # Extract recurring feedback themes
            themes = self._extract_themes(feedbacks)
            for theme, count in themes.most_common(3):
                if count >= 2:
                    extracted.append(Skill(
                        id=self._make_id(f"{run_id}:theme:{theme}"),
                        name=f"Recurring Issue: {theme} ({category})",
                        description=f"'{theme}' appeared in {count}/{len(feedbacks)} feedback rounds",
                        category=category,
                        source_type="failure" if final_score < 0.7 else "success",
                        trigger=f"Working on {category} content",
                        action=f"Preemptively address '{theme}' in early drafts",
                        evidence=f"Appeared {count} times across {len(feedbacks)} iterations",
                        created_at=now,
                        tags=[category, "feedback-pattern", theme],
                    ))

        # 3. Efficiency skill
        if final_score >= 0.8 and iteration_count <= 3:
            extracted.append(Skill(
                id=self._make_id(f"{run_id}:efficient"),
                name=f"Efficient {scenario_id} Generation",
                description=f"Achieved {final_score:.2f} in only {iteration_count} iterations",
                category=category,
                source_type="success",
                trigger=f"Starting a {scenario_id} type document",
                action=f"Use the approach from run {run_id[:8]} as template",
                evidence=f"Score {final_score:.2f} in {iteration_count} iterations",
                created_at=now,
                tags=[category, scenario_id, "efficient"],
            ))

        # 4. Source effectiveness skill
        if sources_used:
            api_counts = Counter(s.get("api", "unknown") for s in sources_used)
            best_api = api_counts.most_common(1)[0] if api_counts else None
            if best_api and best_api[1] >= 3:
                extracted.append(Skill(
                    id=self._make_id(f"{run_id}:source:{best_api[0]}"),
                    name=f"Best Source: {best_api[0]} for {category}",
                    description=f"{best_api[0]} provided {best_api[1]} useful sources",
                    category=category,
                    source_type="success",
                    trigger=f"Searching for sources in {category}",
                    action=f"Prioritize {best_api[0]} for {category} research",
                    evidence=f"{best_api[1]} sources used from {best_api[0]}",
                    created_at=now,
                    tags=[category, "source-strategy", best_api[0]],
                ))

        return extracted

    def extract_with_llm(
        self,
        run_context: str,
        llm_callable: Callable[[str], str],
        category: str = "general",
    ) -> List[Skill]:
        """Extract skills using LLM analysis (richer but costs tokens).

        Args:
            run_context: Full text context from the run.
            llm_callable: Function that accepts a prompt and returns text.
            category: Domain category.
        """
        prompt = f"""Analyze this research run and extract 2-4 reusable skills.

For each skill, provide:
- name: Short descriptive name
- trigger: When should this skill be applied?
- action: What exactly should be done?
- evidence: Why does this work (based on this run)?

Run context:
{run_context[:3000]}

Output as JSON array of objects with keys: name, trigger, action, evidence"""

        try:
            response = llm_callable(prompt)
            # Parse JSON from response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                items = json.loads(json_match.group())
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                return [
                    Skill(
                        id=self._make_id(f"llm:{item.get('name', '')}:{now}"),
                        name=item.get("name", "LLM-extracted skill"),
                        description=f"LLM-extracted from run analysis",
                        category=category,
                        source_type="success",
                        trigger=item.get("trigger", ""),
                        action=item.get("action", ""),
                        evidence=item.get("evidence", ""),
                        created_at=now,
                        tags=[category, "llm-extracted"],
                    )
                    for item in items[:4]
                ]
        except (json.JSONDecodeError, Exception):
            pass
        return []

    # ---- Storage / Retrieval ----

    def save(self, skills: List[Skill]) -> int:
        """Save new skills, deduplicating against existing ones.

        Returns number of new skills added.
        """
        existing_ids = {s.id for s in self._skills}
        added = 0
        for skill in skills:
            if skill.id in existing_ids:
                # Reinforce existing skill
                for s in self._skills:
                    if s.id == skill.id:
                        s.strength = min(2.0, s.strength + 0.2)
                        s.usage_count += 1
                        break
            else:
                # Check for semantic dedup
                if not self._is_duplicate(skill):
                    self._skills.append(skill)
                    existing_ids.add(skill.id)
                    added += 1

        self._persist()
        return added

    def get_skills(
        self,
        category: Optional[str] = None,
        idea: Optional[str] = None,
        source_type: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Skill]:
        """Retrieve relevant skills.

        Args:
            category: Filter by domain.
            idea: Match against idea text (keyword overlap).
            source_type: "success" or "failure".
            max_results: Max skills to return.
        """
        candidates = self._skills

        if category:
            candidates = [s for s in candidates if s.category == category]
        if source_type:
            candidates = [s for s in candidates if s.source_type == source_type]

        if idea:
            query_words = set(idea.lower().split())
            scored = []
            for s in candidates:
                doc_words = set(f"{s.name} {s.trigger} {s.action} {' '.join(s.tags)}".lower().split())
                overlap = len(query_words & doc_words)
                scored.append((overlap * s.strength, s))
            scored.sort(key=lambda x: -x[0])
            return [s for _, s in scored[:max_results] if _ > 0]

        # Sort by strength
        candidates.sort(key=lambda s: -s.strength)
        return candidates[:max_results]

    def format_for_prompt(self, skills: List[Skill]) -> str:
        """Format skills as context for LLM prompt injection."""
        if not skills:
            return ""
        parts = ["## Applicable Skills from Past Experience\n"]
        for i, s in enumerate(skills, 1):
            icon = "✅" if s.source_type == "success" else "⚠️"
            parts.append(f"{i}. {icon} **{s.name}**")
            parts.append(f"   - When: {s.trigger}")
            parts.append(f"   - Do: {s.action}")
            if s.evidence:
                parts.append(f"   - Evidence: {s.evidence}")
        return "\n".join(parts)

    def stats(self) -> Dict[str, Any]:
        """Get skill library statistics."""
        by_cat = Counter(s.category for s in self._skills)
        by_type = Counter(s.source_type for s in self._skills)
        return {
            "total_skills": len(self._skills),
            "by_category": dict(by_cat),
            "by_type": dict(by_type),
            "avg_strength": sum(s.strength for s in self._skills) / max(len(self._skills), 1),
        }

    # ---- Internal ----

    def _is_duplicate(self, new: Skill) -> bool:
        """Check if a skill is semantically duplicate of existing ones."""
        new_words = set(f"{new.name} {new.trigger} {new.action}".lower().split())
        for existing in self._skills:
            if existing.category != new.category:
                continue
            ex_words = set(f"{existing.name} {existing.trigger} {existing.action}".lower().split())
            overlap = len(new_words & ex_words) / max(len(new_words | ex_words), 1)
            if overlap > 0.7:
                return True
        return False

    @staticmethod
    def _extract_themes(feedbacks: List[str]) -> Counter:
        """Extract recurring themes from feedback strings."""
        theme_patterns = [
            "clarity", "evidence", "structure", "citation", "methodology",
            "analysis", "argument", "formatting", "depth", "coherence",
            "novelty", "rigor", "detail", "conciseness", "accuracy",
            "relevance", "originality", "readability", "logic", "data",
        ]
        themes = Counter()
        for fb in feedbacks:
            fb_lower = fb.lower()
            for theme in theme_patterns:
                if theme in fb_lower:
                    themes[theme] += 1
        return themes

    @staticmethod
    def _make_id(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _load(self):
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text(encoding="utf-8"))
                self._skills = [Skill.from_dict(d) for d in data]
            except (json.JSONDecodeError, OSError):
                self._skills = []

    def _persist(self):
        data = [s.to_dict() for s in self._skills]
        self.store_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

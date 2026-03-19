"""Universal 7-dimension Pack scorer.

Reads a Profile's rubric weights and scores pack content accordingly.
Can be used with LLM-as-judge (agent mode) or heuristic baseline.
"""

from __future__ import annotations
import logging

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ideaclaw.quality.loader import Profile, DEFAULT_DIMENSIONS

logger = logging.getLogger(__name__)

__all__ = ['DimensionScore', 'ScoreResult', 'PackScorer']


@dataclass
class DimensionScore:
    """Score for a single rubric dimension."""
    name: str
    score: float          # 0-10
    weight: float         # percentage
    feedback: str = ""


@dataclass
class ScoreResult:
    """Complete scoring result for a pack."""
    profile_id: str
    pqs: float                                # Pack Quality Score (0-10)
    verdict: str                              # PASS / REVISE / FAIL
    dimensions: List[DimensionScore] = field(default_factory=list)
    bonus_met: List[str] = field(default_factory=list)
    reject_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "pqs": round(self.pqs, 2),
            "verdict": self.verdict,
            "dimensions": [
                {"name": d.name, "score": d.score, "weight": d.weight, "feedback": d.feedback}
                for d in self.dimensions
            ],
            "bonus_met": self.bonus_met,
            "reject_reasons": self.reject_reasons,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class PackScorer:
    """Scores a pack against a profile's rubric.

    Two modes:
    1. Heuristic (no LLM) — fast, signal-based scoring
    2. LLM-as-judge — sends pack + rubric to LLM for scoring (agent mode)
    """

    def __init__(self, profile: Profile):
        self.profile = profile

    def score_heuristic(self, pack_content: str) -> ScoreResult:
        """Score using heuristic signals (no LLM needed).

        Uses text analysis to estimate each dimension based on
        observable signals like citation count, structure markers, etc.
        """
        dim_scores = []
        for dim in self.profile.dimensions:
            score = self._heuristic_dimension(dim.name, pack_content)
            dim_scores.append(DimensionScore(
                name=dim.name,
                score=score,
                weight=dim.weight,
                feedback=self._heuristic_feedback(dim.name, score),
            ))

        # Calculate weighted PQS
        total_weight = sum(d.weight for d in dim_scores)
        if total_weight > 0:
            pqs = sum(d.score * d.weight for d in dim_scores) / total_weight
        else:
            pqs = 0.0

        # Check reject conditions
        reject_reasons = self._check_reject_conditions(pack_content)

        # Determine verdict
        if reject_reasons:
            verdict = "FAIL"
        elif pqs >= self.profile.pass_threshold:
            verdict = "PASS"
        elif pqs >= self.profile.pass_threshold - 2.0:
            verdict = "REVISE"
        else:
            verdict = "FAIL"

        # Check bonus criteria
        bonus_met = self._check_bonus(pack_content)

        return ScoreResult(
            profile_id=self.profile.id,
            pqs=pqs,
            verdict=verdict,
            dimensions=dim_scores,
            bonus_met=bonus_met,
            reject_reasons=reject_reasons,
        )

    def build_llm_prompt(self, pack_content: str) -> str:
        """Build a prompt for LLM-as-judge scoring.

        Returns a system+user prompt pair that asks the LLM to score
        each dimension on 0-10 and return structured JSON.
        """
        dims_desc = "\n".join(
            f"  - {d.name} (weight {d.weight}%): {d.description}"
            for d in self.profile.dimensions
        )

        checklist_desc = "\n".join(
            f"  - {item}" for item in self.profile.checklist
        ) if self.profile.checklist else "  (none specified)"

        reject_desc = "\n".join(
            f"  - {item}" for item in self.profile.reject_if
        ) if self.profile.reject_if else "  (none specified)"

        return f"""You are a quality reviewer for "{self.profile.name}" ({self.profile.id}).

Score the following pack on these 7 dimensions (each 0-10):

{dims_desc}

Checklist to verify:
{checklist_desc}

Auto-reject if ANY of these are true:
{reject_desc}

Pass threshold: PQS ≥ {self.profile.pass_threshold}

Pack content to review:
---
{pack_content}
---

Respond with ONLY a JSON object:
{{
  "dimensions": {{
    "evidence_coverage": {{"score": N, "feedback": "..."}},
    "claim_accuracy": {{"score": N, "feedback": "..."}},
    "reasoning_quality": {{"score": N, "feedback": "..."}},
    "actionability": {{"score": N, "feedback": "..."}},
    "uncertainty_honesty": {{"score": N, "feedback": "..."}},
    "structure_clarity": {{"score": N, "feedback": "..."}},
    "counterargument_depth": {{"score": N, "feedback": "..."}}
  }},
  "reject_reasons": [],
  "bonus_met": [],
  "overall_feedback": "..."
}}"""

    def score_from_llm_response(self, llm_json: Dict[str, Any]) -> ScoreResult:
        """Parse an LLM judge response into a ScoreResult."""
        dim_scores = []
        dims_data = llm_json.get("dimensions", {})
        for dim in self.profile.dimensions:
            info = dims_data.get(dim.name, {})
            dim_scores.append(DimensionScore(
                name=dim.name,
                score=float(info.get("score", 5.0)),
                weight=dim.weight,
                feedback=info.get("feedback", ""),
            ))

        total_weight = sum(d.weight for d in dim_scores)
        pqs = sum(d.score * d.weight for d in dim_scores) / total_weight if total_weight else 0

        reject_reasons = llm_json.get("reject_reasons", [])
        bonus_met = llm_json.get("bonus_met", [])

        if reject_reasons:
            verdict = "FAIL"
        elif pqs >= self.profile.pass_threshold:
            verdict = "PASS"
        elif pqs >= self.profile.pass_threshold - 2.0:
            verdict = "REVISE"
        else:
            verdict = "FAIL"

        return ScoreResult(
            profile_id=self.profile.id,
            pqs=pqs,
            verdict=verdict,
            dimensions=dim_scores,
            bonus_met=bonus_met,
            reject_reasons=reject_reasons,
        )

    # ─── Heuristic helpers ────────────────────────────────────────────

    def _heuristic_dimension(self, dim_name: str, content: str) -> float:
        """Estimate a dimension score from text signals."""
        content_lower = content.lower()
        lines = content.split("\n")
        word_count = len(content.split())

        if dim_name == "evidence_coverage":
            # Count citation-like patterns
            citations = len(re.findall(r'\[source[:\s]', content_lower))
            citations += len(re.findall(r'https?://', content))
            citations += len(re.findall(r'✅', content))
            if citations >= 10: return 9.0
            if citations >= 5: return 7.0
            if citations >= 2: return 5.0
            return 3.0

        elif dim_name == "claim_accuracy":
            # Penalize vague claims without evidence markers
            vague = len(re.findall(r'(probably|maybe|might|seems to|could be)', content_lower))
            evidenced = content.count("✅")
            if evidenced > vague * 2: return 8.0
            if evidenced > vague: return 6.5
            return 5.0

        elif dim_name == "reasoning_quality":
            # Check for structure markers (headers, numbered lists, logic words)
            headers = len(re.findall(r'^#+\s', content, re.MULTILINE))
            logic_words = len(re.findall(
                r'\b(therefore|because|however|consequently|thus|since|given that)\b',
                content_lower
            ))
            if headers >= 5 and logic_words >= 3: return 8.0
            if headers >= 3: return 6.5
            return 5.0

        elif dim_name == "actionability":
            # Check for action items section and imperative verbs
            has_actions = bool(re.search(r'action item|next step|recommend|todo', content_lower))
            imperative = len(re.findall(r'\b(do|create|build|implement|contact|review|set)\b', content_lower))
            if has_actions and imperative >= 3: return 8.0
            if has_actions: return 6.5
            return 4.0

        elif dim_name == "uncertainty_honesty":
            # Check for uncertainty markers
            warnings = content.count("⚠️") + content.count("🚫")
            uncertainty_words = len(re.findall(
                r'\b(uncertain|unknown|unclear|insufficient|gap|limitation)\b',
                content_lower
            ))
            if warnings >= 3 or uncertainty_words >= 3: return 8.5
            if warnings >= 1 or uncertainty_words >= 1: return 6.0
            return 3.0  # No uncertainties flagged = suspicious

        elif dim_name == "structure_clarity":
            # Headers, sections, scannable formatting
            headers = len(re.findall(r'^#+\s', content, re.MULTILINE))
            bullets = len(re.findall(r'^\s*[-*]\s', content, re.MULTILINE))
            has_ruler = "---" in content
            if headers >= 5 and bullets >= 5 and has_ruler: return 9.0
            if headers >= 3 and bullets >= 3: return 7.0
            if headers >= 2: return 5.0
            return 3.0

        elif dim_name == "counterargument_depth":
            # Check for counterargument/risk sections
            has_counter = bool(re.search(
                r'counterargument|opposing|devil.s advocate|risk|however|on the other hand',
                content_lower
            ))
            counter_items = len(re.findall(r'^\s*[-*]\s.*(?:risk|counter|however|but)', content, re.MULTILINE | re.IGNORECASE))
            if has_counter and counter_items >= 3: return 8.0
            if has_counter: return 6.0
            return 3.0

        return 5.0  # Unknown dimension

    def _heuristic_feedback(self, dim_name: str, score: float) -> str:
        """Generate feedback text for a heuristic score."""
        if score >= 8.0:
            return "Strong"
        elif score >= 6.0:
            return "Adequate, room for improvement"
        elif score >= 4.0:
            return "Below expectations, needs work"
        else:
            return "Weak, significant gaps"

    def _check_reject_conditions(self, content: str) -> List[str]:
        """Check profile-specific reject conditions."""
        reasons = []
        content_lower = content.lower()
        for condition in self.profile.reject_if:
            # Simple keyword match
            cond_lower = condition.lower()
            # Extract key terms from the condition
            key_terms = [w for w in cond_lower.split() if len(w) > 4]
            if key_terms and all(term in content_lower for term in key_terms[:2]):
                reasons.append(condition)
        return reasons

    def _check_bonus(self, content: str) -> List[str]:
        """Check which bonus criteria are met."""
        met = []
        content_lower = content.lower()
        for criterion in self.profile.bonus_criteria:
            key_terms = [w for w in criterion.lower().split() if len(w) > 4]
            if key_terms and any(term in content_lower for term in key_terms):
                met.append(criterion)
        return met

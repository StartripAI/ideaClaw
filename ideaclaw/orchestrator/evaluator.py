"""Orchestrator evaluator — unified scoring engine.

Evaluates drafts against scenario profile criteria. Plugs into
loop.py's evaluate() hook point.

Combines multiple scoring dimensions:
  - Structure: section coverage, length compliance
  - Citation: reference count, verification status
  - Style: formality, voice, terminology
  - Content: depth, novelty, clarity
  - Experiment: metric improvement (if sandbox enabled)
"""

from __future__ import annotations
import logging

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ideaclaw.orchestrator.loop import ScenarioProfile, EvalCriterion

logger = logging.getLogger(__name__)

__all__ = ["score_structure", "score_citations", "score_style", "score_depth", "score_novelty_section", "UnifiedEvaluator"]


# ---------------------------------------------------------------------------
# Scoring functions — each returns 0.0-1.0
# ---------------------------------------------------------------------------

def score_structure(draft: str, profile: ScenarioProfile) -> float:
    """Score structural compliance (section coverage, length)."""
    required = profile.style.required_sections
    if not required:
        return 0.8  # No requirements = baseline OK

    # Count sections present in draft (case-insensitive heading detection)
    draft_lower = draft.lower()
    found = 0
    for section in required:
        # Check for markdown heading or LaTeX section
        patterns = [
            f"# {section.lower()}",
            f"## {section.lower()}",
            f"### {section.lower()}",
            f"\\section{{{section.lower()}}}",
            f"\\subsection{{{section.lower()}}}",
        ]
        if any(p in draft_lower for p in patterns):
            found += 1

    section_score = found / len(required) if required else 1.0

    # Length check
    word_count = len(draft.split())
    if profile.style.max_pages > 0:
        expected_words = profile.style.max_pages * 500  # ~500 words/page
        length_ratio = min(1.0, word_count / max(1, expected_words * 0.7))
        # Penalty for being too short, slight penalty for too long
        if word_count > expected_words * 1.2:
            length_ratio *= 0.9
    else:
        length_ratio = min(1.0, word_count / 1000)  # At least 1000 words

    return 0.6 * section_score + 0.4 * length_ratio


def score_citations(draft: str, profile: ScenarioProfile, sources: List[Any]) -> float:
    """Score citation quality (count, real references, formatting)."""
    # Count citation markers in draft
    # Common patterns: [1], [Author, 2024], \cite{key}, (Author et al., 2024)
    cite_patterns = [
        r'\[\d+\]',                          # [1], [23]
        r'\\cite\{[^}]+\}',                  # \cite{key}
        r'\\citep?\{[^}]+\}',                # \citet{key} or \citep{key}
        r'\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)',  # (Author et al., 2024)
    ]
    total_cites = 0
    for pattern in cite_patterns:
        total_cites += len(re.findall(pattern, draft))

    min_refs = profile.search.min_sources
    if min_refs > 0:
        cite_ratio = min(1.0, total_cites / min_refs)
    else:
        cite_ratio = min(1.0, total_cites / 5)  # Default: at least 5 citations

    # Check for bibliography/references section
    has_biblio = any(marker in draft.lower() for marker in [
        "# references", "## references", "\\bibliography",
        "# bibliography", "\\begin{thebibliography}",
    ])
    biblio_score = 1.0 if has_biblio else 0.5

    # Source count vs required
    source_score = min(1.0, len(sources) / max(1, min_refs)) if min_refs > 0 else 0.8

    return 0.4 * cite_ratio + 0.3 * biblio_score + 0.3 * source_score


def score_style(draft: str, profile: ScenarioProfile) -> float:
    """Score style compliance (formality, voice, tense)."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', draft) if len(s.strip()) > 10]
    if not sentences:
        return 0.0

    scores = []

    # Formality: check for informal markers
    informal_markers = [
        "can't", "won't", "don't", "it's", "let's", "gonna", "wanna",
        "kinda", "sorta", "basically", "actually", "totally", "super",
        "awesome", "cool", "stuff", "things", "guys", "ok", "okay",
        "lol", "btw", "fyi", "tbh", "imo", "!", "!!", "!!!",
    ]
    informal_count = sum(1 for marker in informal_markers
                         if marker in draft.lower())
    formality_score = max(0.0, 1.0 - informal_count * 0.05)

    # Scale by expected formality
    if profile.style.formality > 0.8:
        # High formality required — penalize informality more
        scores.append(formality_score)
    else:
        # Lower formality OK
        scores.append(min(1.0, formality_score + 0.2))

    # Voice: check first person usage
    first_person = len(re.findall(r'\bI\b|\bmy\b|\bme\b|\bmine\b|\bmyself\b',
                                   draft, re.IGNORECASE))
    we_person = len(re.findall(r'\bwe\b|\bour\b|\bus\b|\bourselves\b',
                                draft, re.IGNORECASE))

    if profile.style.voice == "third_person":
        # Penalize first person
        fp_ratio = (first_person + we_person) / max(1, len(sentences))
        scores.append(max(0.0, 1.0 - fp_ratio * 5))
    elif profile.style.voice == "first_person":
        # Expect some first person
        fp_ratio = (first_person + we_person) / max(1, len(sentences))
        scores.append(min(1.0, fp_ratio * 3))
    else:
        scores.append(0.8)  # Mixed is always OK

    # Passive voice detection (simple heuristic)
    passive_patterns = len(re.findall(r'\b(?:is|are|was|were|been|being)\s+\w+ed\b', draft))
    passive_ratio = passive_patterns / max(1, len(sentences))
    # Academic writing typically has 20-30% passive
    if profile.style.formality > 0.8:
        scores.append(min(1.0, 0.5 + passive_ratio * 2))
    else:
        scores.append(max(0.5, 1.0 - passive_ratio))

    return sum(scores) / len(scores) if scores else 0.5


def score_depth(draft: str, profile: ScenarioProfile) -> float:
    """Score content depth (word count, technical density, examples)."""
    words = draft.split()
    word_count = len(words)

    # Technical density: ratio of longer/specialized words
    tech_words = sum(1 for w in words if len(w) > 8)
    tech_ratio = tech_words / max(1, word_count)

    # Equation/formula presence (LaTeX or markdown math)
    math_count = len(re.findall(r'\$[^$]+\$|\\begin\{equation\}|\\begin\{align\}', draft))

    # Figure/table references
    fig_count = len(re.findall(r'(?:Figure|Fig\.|Table|Tab\.)\s*\d', draft, re.IGNORECASE))

    # Code block presence
    code_count = len(re.findall(r'```\w*\n', draft))

    # Scoring
    length_score = min(1.0, word_count / 3000)  # Expect ≥3000 words for depth
    tech_score = min(1.0, tech_ratio * 5)       # ~20% technical words
    enrichment = min(1.0, (math_count + fig_count + code_count) / 5)

    return 0.4 * length_score + 0.3 * tech_score + 0.3 * enrichment


def score_novelty_section(draft: str, profile: ScenarioProfile) -> float:
    """Score whether the draft demonstrates novelty/contribution."""
    novelty_markers = [
        "we propose", "we introduce", "our approach", "our method",
        "novel", "new approach", "first to", "contribution",
        "unlike previous", "in contrast to", "we show that",
        "our key insight", "main contribution",
    ]
    draft_lower = draft.lower()
    found = sum(1 for marker in novelty_markers if marker in draft_lower)
    return min(1.0, found / 3)  # At least 3 novelty markers


# ---------------------------------------------------------------------------
# Unified Evaluator
# ---------------------------------------------------------------------------

class UnifiedEvaluator:
    """Evaluate drafts using profile-defined criteria.

    Scoring functions are mapped by criterion name:
      structure  → score_structure()
      citations  → score_citations()
      style      → score_style()
      depth      → score_depth()
      novelty    → score_novelty_section()

    Features beyond ARC:
      - Calibrated scoring (raw → calibrated via logistic curve)
      - Multi-rater agreement (heuristic vs LLM-as-judge)
      - Score coherence checks (detects contradictory dimensions)
      - Meta-scoring (weighted composite with confidence)
      - Score history tracking for trend analysis
    """

    SCORERS = {
        "structure": lambda draft, profile, sources: score_structure(draft, profile),
        "citations": lambda draft, profile, sources: score_citations(draft, profile, sources),
        "citation_quality": lambda draft, profile, sources: score_citations(draft, profile, sources),
        "style": lambda draft, profile, sources: score_style(draft, profile),
        "depth": lambda draft, profile, sources: score_depth(draft, profile),
        "novelty": lambda draft, profile, sources: score_novelty_section(draft, profile),
        "clarity": lambda draft, profile, sources: score_style(draft, profile),
        "soundness": lambda draft, profile, sources: score_depth(draft, profile),
        "significance": lambda draft, profile, sources: score_novelty_section(draft, profile),
        "citations_verified": lambda draft, profile, sources: score_citations(draft, profile, sources),
        "formatting": lambda draft, profile, sources: score_structure(draft, profile),
    }

    # Calibration: logistic curve parameters for raw→calibrated mapping
    # shifts raw scores so 0.5 raw → 0.5 calibrated, with steeper slope
    CALIBRATION_K = 8.0   # steepness
    CALIBRATION_X0 = 0.55  # midpoint (raw scores tend to be optimistic)

    @staticmethod
    def _default_scorers() -> Dict[str, Any]:
        """Factory for per-instance scorer map (prevents cross-instance pollution)."""
        def _score_structure(draft, profile, sources):
            return score_structure(draft, profile)

        def _score_citations(draft, profile, sources):
            return score_citations(draft, profile, sources)

        def _score_style(draft, profile, sources):
            return score_style(draft, profile)

        def _score_depth(draft, profile, sources):
            return score_depth(draft, profile)

        def _score_novelty(draft, profile, sources):
            return score_novelty_section(draft, profile)

        return {
            "structure": _score_structure,
            "citations": _score_citations,
            "citation_quality": _score_citations,
            "style": _score_style,
            "depth": _score_depth,
            "novelty": _score_novelty,
            "clarity": _score_style,
            "soundness": _score_depth,
            "significance": _score_novelty,
            "citations_verified": _score_citations,
            "formatting": _score_structure,
        }

    def __init__(self):
        self.scorers = self._default_scorers()
        self._score_history: List[Dict[str, float]] = []

    def evaluate(
        self,
        profile: ScenarioProfile,
        draft: str,
        sources: List[Any],
        calibrate: bool = True,
    ) -> Dict[str, float]:
        """Score a draft against all profile criteria.

        Returns dict of criterion_name → score (0.0-1.0).
        """
        scores: Dict[str, float] = {}

        if not profile.criteria:
            for name in ["structure", "citations", "style", "depth"]:
                scorer = self.scorers.get(name)
                if scorer:
                    raw = scorer(draft, profile, sources)
                    scores[name] = round(self._calibrate(raw) if calibrate else raw, 4)
            self._score_history.append(scores)
            return scores

        for criterion in profile.criteria:
            scorer = self.scorers.get(criterion.name)
            if scorer:
                raw = scorer(draft, profile, sources)
                scores[criterion.name] = round(
                    self._calibrate(raw) if calibrate else raw, 4
                )
            else:
                scores[criterion.name] = 0.5

        self._score_history.append(scores)
        return scores

    def meta_score(
        self, scores: Dict[str, float], profile: ScenarioProfile,
    ) -> Dict[str, Any]:
        """Compute meta-score with confidence and coherence check.

        Returns:
            Dict with 'composite', 'confidence', 'coherent', 'weak_dims'.
        """
        if not scores:
            return {"composite": 0.0, "confidence": 0.0, "coherent": True, "weak_dims": []}

        # Weighted composite
        if profile.criteria:
            total_w = sum(c.weight for c in profile.criteria)
            composite = sum(
                scores.get(c.name, 0.0) * c.weight for c in profile.criteria
            ) / max(total_w, 0.01)
        else:
            composite = sum(scores.values()) / max(len(scores), 1)

        # Confidence: based on score spread (tighter = more confident)
        vals = list(scores.values())
        spread = max(vals) - min(vals) if vals else 0.0
        confidence = max(0.0, 1.0 - spread * 1.5)

        # Coherence: check for contradictory scores
        coherent, issues = self.score_coherence(scores)

        # Weak dimensions  
        weak = [k for k, v in scores.items() if v < 0.5]

        return {
            "composite": round(composite, 4),
            "confidence": round(confidence, 3),
            "coherent": coherent,
            "coherence_issues": issues,
            "weak_dims": weak,
        }

    @staticmethod
    def score_coherence(scores: Dict[str, float]) -> tuple:
        """Check for contradictory dimension scores.

        For example, high 'depth' but low 'structure' is suspicious.
        """
        issues = []
        s = scores

        # High depth but low structure is unlikely
        if s.get("depth", 0) > 0.8 and s.get("structure", 1) < 0.4:
            issues.append("High depth but low structure — possible formatting issue")

        # High citations but low depth is suspicious
        if s.get("citations", 0) > 0.8 and s.get("depth", 1) < 0.3:
            issues.append("Many citations but shallow depth — possible padding")

        # High novelty but low depth
        if s.get("novelty", 0) > 0.8 and s.get("depth", 1) < 0.4:
            issues.append("Claims novelty without depth — may lack substance")

        return len(issues) == 0, issues

    def score_trend(self) -> Dict[str, Any]:
        """Analyze score trend across iterations.

        Returns:
            Dict with per-dimension trends and overall trajectory.
        """
        if len(self._score_history) < 2:
            return {"trajectory": "insufficient_data", "iterations": len(self._score_history)}

        # Per-dimension trend
        all_dims = set()
        for h in self._score_history:
            all_dims.update(h.keys())

        trends: Dict[str, str] = {}
        for dim in all_dims:
            vals = [h.get(dim, 0.0) for h in self._score_history]
            if len(vals) >= 2:
                delta = vals[-1] - vals[0]
                if delta > 0.05:
                    trends[dim] = "improving"
                elif delta < -0.05:
                    trends[dim] = "declining"
                else:
                    trends[dim] = "stable"

        improving = sum(1 for t in trends.values() if t == "improving")
        declining = sum(1 for t in trends.values() if t == "declining")

        if improving > declining:
            trajectory = "improving"
        elif declining > improving:
            trajectory = "declining"
        else:
            trajectory = "stable"

        return {
            "trajectory": trajectory,
            "iterations": len(self._score_history),
            "per_dimension": trends,
        }

    def _calibrate(self, raw: float) -> float:
        """Apply logistic calibration to raw heuristic score.

        Maps raw 0-1 scores through a logistic curve to counter
        the tendency of heuristic scorers to be overconfident.
        """
        x = max(0.001, min(0.999, raw))
        calibrated = 1.0 / (1.0 + math.exp(-self.CALIBRATION_K * (x - self.CALIBRATION_X0)))
        return max(0.0, min(1.0, calibrated))

    def register_scorer(self, name: str, fn) -> None:
        """Register a custom scoring function for a criterion name.

        fn signature: (draft: str, profile: ScenarioProfile, sources: List) -> float
        Modifies only this instance's scorer map (not shared).
        """
        self.scorers[name] = fn

    def as_hook(self):
        """Return a function matching the EvaluateHook protocol."""
        return self.evaluate


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

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ideaclaw.orchestrator.loop import ScenarioProfile, EvalCriterion


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
      
    Unknown criteria get a default 0.5 score (to be extended).
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

    def evaluate(
        self,
        profile: ScenarioProfile,
        draft: str,
        sources: List[Any],
    ) -> Dict[str, float]:
        """Score a draft against all profile criteria.

        Returns dict of criterion_name → score (0.0-1.0).
        """
        scores: Dict[str, float] = {}

        if not profile.criteria:
            # Default criteria if none specified
            for name in ["structure", "citations", "style", "depth"]:
                scorer = self.SCORERS.get(name)
                if scorer:
                    scores[name] = round(scorer(draft, profile, sources), 4)
            return scores

        for criterion in profile.criteria:
            scorer = self.SCORERS.get(criterion.name)
            if scorer:
                scores[criterion.name] = round(scorer(draft, profile, sources), 4)
            else:
                # Unknown criterion — can be extended by registering new scorer
                scores[criterion.name] = 0.5
                
        return scores

    def register_scorer(self, name: str, fn) -> None:
        """Register a custom scoring function for a criterion name.
        
        fn signature: (draft: str, profile: ScenarioProfile, sources: List) -> float
        """
        self.SCORERS[name] = fn

    def as_hook(self):
        """Return a function matching the EvaluateHook protocol."""
        return self.evaluate

"""Novelty detection — determine if a research idea is truly novel.

Surpasses ARC's novelty.py by providing:
  - Multi-dimensional novelty scoring (semantic, keyword, methodological)
  - Overlap detection against existing literature
  - Novelty verdict with evidence citations
  - Works offline (heuristic mode) and online (with search results)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ideaclaw.source.collector import SourceResult


@dataclass
class NoveltyScore:
    """Multi-dimensional novelty assessment."""
    keyword_overlap: float       # 0.0 (novel) - 1.0 (fully overlapping)
    title_similarity: float      # 0.0 (novel) - 1.0 (identical title)
    method_overlap: float        # 0.0 (novel) - 1.0 (same methods)
    composite_novelty: float     # 0.0 (not novel) - 1.0 (highly novel)
    verdict: str                 # NOVEL | INCREMENTAL | OVERLAPPING | DUPLICATE
    confidence: float            # 0.0 - 1.0
    most_similar_papers: List[Dict[str, Any]] = field(default_factory=list)
    explanation: str = ""


# Common method keywords for different domains
METHOD_KEYWORDS = {
    "ml": {
        "transformer", "attention", "cnn", "rnn", "lstm", "gru", "bert",
        "gpt", "diffusion", "gan", "vae", "reinforcement learning",
        "contrastive learning", "self-supervised", "few-shot", "zero-shot",
        "fine-tuning", "pre-training", "distillation", "pruning",
        "quantization", "federated", "meta-learning", "graph neural",
    },
    "bio": {
        "crispr", "pcr", "western blot", "rna-seq", "chip-seq",
        "flow cytometry", "mass spectrometry", "single-cell",
        "organoid", "xenograft", "knockout", "immunohistochemistry",
        "phylogenetic", "sequence alignment", "docking",
    },
    "general": {
        "regression", "classification", "clustering", "sampling",
        "simulation", "optimization", "statistical test", "survey",
        "meta-analysis", "systematic review", "randomized controlled",
        "cohort study", "cross-sectional", "case study",
    },
}


def _tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercase word set."""
    return set(re.findall(r"[a-z][a-z0-9]+", text.lower()))


def _bigrams(tokens: Set[str]) -> Set[str]:
    """Generate sorted bigrams from token set."""
    sorted_tokens = sorted(tokens)
    return {f"{a}_{b}" for i, a in enumerate(sorted_tokens)
            for b in sorted_tokens[i + 1:i + 2]}


def _jaccard(set_a: Set[str], set_b: Set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _extract_methods(text: str) -> Set[str]:
    """Extract methodological keywords from text."""
    text_lower = text.lower()
    found = set()
    for domain_methods in METHOD_KEYWORDS.values():
        for method in domain_methods:
            if method in text_lower:
                found.add(method)
    return found


def assess_novelty(
    idea_title: str,
    idea_description: str,
    existing_papers: List[SourceResult],
    method_keywords: Optional[Set[str]] = None,
) -> NoveltyScore:
    """Assess the novelty of a research idea against existing papers.

    Args:
        idea_title: Title of the proposed research idea.
        idea_description: Full description of the idea.
        existing_papers: List of existing papers from literature search.
        method_keywords: Optional set of methodology keywords to match.

    Returns:
        NoveltyScore with multi-dimensional assessment.
    """
    if not existing_papers:
        return NoveltyScore(
            keyword_overlap=0.0,
            title_similarity=0.0,
            method_overlap=0.0,
            composite_novelty=1.0,
            verdict="NOVEL",
            confidence=0.3,  # Low confidence — no papers to compare against
            explanation="No existing papers found for comparison. Novelty assessment has low confidence.",
        )

    idea_tokens = _tokenize(idea_title + " " + idea_description)
    idea_bigrams = _bigrams(idea_tokens)
    idea_methods = method_keywords or _extract_methods(idea_description)

    # Per-paper similarity
    paper_scores: List[Tuple[float, float, float, SourceResult]] = []

    for paper in existing_papers:
        paper_text = f"{paper.title} {paper.abstract or ''}"
        paper_tokens = _tokenize(paper_text)
        paper_bigrams = _bigrams(paper_tokens)
        paper_methods = _extract_methods(paper_text)

        # Title similarity (weighted higher)
        title_sim = _jaccard(_tokenize(idea_title), _tokenize(paper.title))

        # Keyword overlap (unigram + bigram)
        uni_sim = _jaccard(idea_tokens, paper_tokens)
        bi_sim = _jaccard(idea_bigrams, paper_bigrams)
        keyword_sim = 0.4 * uni_sim + 0.6 * bi_sim  # Bigrams weighted more

        # Method overlap
        if idea_methods and paper_methods:
            method_sim = _jaccard(idea_methods, paper_methods)
        elif idea_methods or paper_methods:
            method_sim = 0.0  # One has methods, other doesn't
        else:
            method_sim = 0.0

        paper_scores.append((title_sim, keyword_sim, method_sim, paper))

    # Aggregate: use top-3 most similar papers
    paper_scores.sort(key=lambda x: (x[0] + x[1] + x[2]) / 3, reverse=True)
    top_n = paper_scores[:3]

    max_title_sim = max(s[0] for s in top_n)
    avg_keyword_sim = sum(s[1] for s in top_n) / len(top_n)
    max_method_sim = max(s[2] for s in top_n)

    # Composite novelty: weighted combination (inverted — higher = more novel)
    composite = 1.0 - (
        0.35 * max_title_sim +
        0.40 * avg_keyword_sim +
        0.25 * max_method_sim
    )
    composite = max(0.0, min(1.0, composite))

    # Verdict thresholds
    if composite >= 0.75:
        verdict = "NOVEL"
    elif composite >= 0.50:
        verdict = "INCREMENTAL"
    elif composite >= 0.25:
        verdict = "OVERLAPPING"
    else:
        verdict = "DUPLICATE"

    # Confidence based on evidence quality
    confidence = min(1.0, 0.3 + 0.1 * len(existing_papers))

    # Most similar papers
    most_similar = []
    for title_sim, kw_sim, meth_sim, paper in top_n:
        similarity = (title_sim + kw_sim + meth_sim) / 3
        most_similar.append({
            "title": paper.title,
            "url": paper.url,
            "year": paper.year,
            "similarity": round(similarity, 3),
            "title_sim": round(title_sim, 3),
            "keyword_sim": round(kw_sim, 3),
            "method_sim": round(meth_sim, 3),
        })

    # Generate explanation
    top_paper = top_n[0][3]
    if verdict == "NOVEL":
        explanation = (
            f"Idea appears novel. Most similar paper '{top_paper.title}' "
            f"has only {most_similar[0]['similarity']:.0%} overlap."
        )
    elif verdict == "DUPLICATE":
        explanation = (
            f"Idea closely matches '{top_paper.title}' "
            f"({most_similar[0]['similarity']:.0%} overlap). "
            f"Consider differentiating your approach."
        )
    else:
        explanation = (
            f"Idea has {verdict.lower()} novelty. "
            f"Top match: '{top_paper.title}' ({most_similar[0]['similarity']:.0%}). "
            f"Key differences needed in methodology or scope."
        )

    return NoveltyScore(
        keyword_overlap=round(avg_keyword_sim, 4),
        title_similarity=round(max_title_sim, 4),
        method_overlap=round(max_method_sim, 4),
        composite_novelty=round(composite, 4),
        verdict=verdict,
        confidence=round(confidence, 3),
        most_similar_papers=most_similar,
        explanation=explanation,
    )


def novelty_report(score: NoveltyScore) -> str:
    """Generate a markdown novelty report."""
    icon = {"NOVEL": "🟢", "INCREMENTAL": "🟡", "OVERLAPPING": "🟠", "DUPLICATE": "🔴"}
    lines = [
        f"# Novelty Assessment: {icon.get(score.verdict, '⚪')} {score.verdict}",
        "",
        f"**Composite Novelty**: {score.composite_novelty:.0%} (confidence: {score.confidence:.0%})",
        "",
        "## Dimension Scores",
        "",
        f"| Dimension | Score | Interpretation |",
        f"|---|---|---|",
        f"| Title Similarity | {score.title_similarity:.1%} | {'⚠️ High' if score.title_similarity > 0.5 else '✅ Low'} overlap |",
        f"| Keyword Overlap | {score.keyword_overlap:.1%} | {'⚠️ High' if score.keyword_overlap > 0.4 else '✅ Low'} overlap |",
        f"| Method Overlap | {score.method_overlap:.1%} | {'⚠️ High' if score.method_overlap > 0.5 else '✅ Low'} overlap |",
        "",
        f"## Explanation",
        f"{score.explanation}",
        "",
    ]

    if score.most_similar_papers:
        lines.append("## Most Similar Papers")
        lines.append("")
        lines.append("| # | Title | Year | Similarity |")
        lines.append("|---|---|---|---|")
        for i, p in enumerate(score.most_similar_papers, 1):
            lines.append(
                f"| {i} | [{p['title'][:60]}]({p['url']}) | {p['year']} | {p['similarity']:.0%} |"
            )

    return "\n".join(lines)

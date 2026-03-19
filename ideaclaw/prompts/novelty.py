"""Novelty assessment prompts — LLM-as-judge for novelty evaluation.

Provides prompts for:
  - Novelty assessment given existing literature
  - Differentiation suggestions
  - Research gap identification
  - Concurrent work detection
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

__all__ = ["NOVELTY_ASSESSMENT_SYSTEM", "NOVELTY_ASSESSMENT_USER", "GAP_IDENTIFICATION_SYSTEM", "GAP_IDENTIFICATION_USER", "CONCURRENT_WORK_CHECK", "get_novelty_prompt", "get_gap_prompt"]


NOVELTY_ASSESSMENT_SYSTEM = """\
You are a NOVELTY ASSESSMENT EXPERT with comprehensive knowledge of the academic landscape.
Your task is to determine whether a research idea is truly novel.
You are brutally honest — if an idea has been done before, you say so clearly.
You distinguish between: no prior work, incremental improvement, novel combination, genuine novelty.
"""

NOVELTY_ASSESSMENT_USER = """\
Assess the novelty of this research idea against the existing literature.

RESEARCH IDEA:
{idea}

EXISTING LITERATURE (most similar papers):
{literature}

Provide your assessment in this format:

## Novelty Verdict
[NOVEL / INCREMENTAL / OVERLAPPING / DUPLICATE]

## Novelty Score
[0.0-1.0, where 1.0 = completely novel, 0.0 = exact duplicate]

## Confidence
[0.0-1.0, based on how well you know this area]

## Analysis

### What's New (if anything)
- [specific novel element 1]
- [specific novel element 2]

### What's Been Done Before
- [specific overlap with Paper X] — similarity: [high/medium/low]
- [specific overlap with Paper Y] — similarity: [high/medium/low]

### Most Similar Paper
Title: [paper title]
Similarity: [percentage]
Key difference from proposed idea: [explanation]

### Differentiation Suggestions
If the idea is not sufficiently novel, suggest how to make it more novel:
1. [suggestion 1]
2. [suggestion 2]
3. [suggestion 3]

### Research Gaps Identified
Based on the literature review, these related gaps could be explored:
1. [gap 1]
2. [gap 2]
"""

GAP_IDENTIFICATION_SYSTEM = """\
You are a research trend analyst who identifies under-explored research gaps.
Given a set of papers in a field, you identify what HASN'T been done yet.
"""

GAP_IDENTIFICATION_USER = """\
Analyze these papers and identify research gaps.

PAPERS:
{papers}

FIELD: {domain}

For each gap:
1. **Gap Description**: What hasn't been explored?
2. **Potential Impact**: Why would filling this gap matter?
3. **Feasibility**: How hard would it be to address? [Easy/Medium/Hard]
4. **Required Resources**: What would be needed?
5. **Suggested Approach**: Brief sketch of how to tackle it.

Identify at least 5 gaps, ranked by potential impact.
"""

CONCURRENT_WORK_CHECK = """\
Based on recent publications and preprints, assess whether anyone is likely
working on the same or very similar idea concurrently.

IDEA: {idea}
DOMAIN: {domain}
RECENT PAPERS (last 6 months): {recent_papers}

Consider:
1. Are there preprints on closely related topics?
2. Are key research groups in this area likely pursuing similar directions?
3. What's the risk of being "scooped"?
4. How quickly should the authors execute to maintain novelty?
"""


def get_novelty_prompt(idea: str, literature: str = "") -> dict:
    """Get a novelty assessment prompt."""
    return {
        "system": NOVELTY_ASSESSMENT_SYSTEM,
        "user": NOVELTY_ASSESSMENT_USER.format(
            idea=idea,
            literature=literature or "(No literature provided — assess based on general knowledge.)",
        ),
    }


def get_gap_prompt(papers: str, domain: str = "general") -> dict:
    """Get a research gap identification prompt."""
    return {
        "system": GAP_IDENTIFICATION_SYSTEM,
        "user": GAP_IDENTIFICATION_USER.format(papers=papers, domain=domain),
    }

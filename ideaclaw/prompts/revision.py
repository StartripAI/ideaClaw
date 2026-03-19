"""Revision prompts — targeted improvement instructions per evaluation dimension.

Given evaluation scores and feedback, generates specific revision instructions
that tell the LLM exactly what to improve and how.

Covers 10 revision dimensions:
  structure, depth, citations, style, novelty, soundness,
  significance, clarity, reproducibility, limitations

Usage:
    from ideaclaw.prompts.revision import get_revision_prompt

logger = logging.getLogger(__name__)

__all__ = ['REVISION_INSTRUCTIONS', 'REVISION_TEMPLATE', 'get_revision_prompt', 'get_revision_dimensions']
    prompt = get_revision_prompt(scores, draft, profile)
"""

from __future__ import annotations
import logging

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Dimension-specific Revision Instructions
# ---------------------------------------------------------------------------

REVISION_INSTRUCTIONS = {
    "structure": {
        "threshold": 0.7,
        "mild": """\
STRUCTURE IMPROVEMENT (minor):
- Verify heading hierarchy is consistent (# → ## → ### only)
- Ensure each section has a clear topic sentence
- Add transitions between major sections
- Check that the conclusion echoes the introduction's claims
""",
        "severe": """\
STRUCTURE IMPROVEMENT (major):
- REORGANIZE the paper following this structure:
  1. Introduction (problem → gap → contribution → outline)
  2. Related Work (grouped by approach, compare don't list)
  3. Method (formal problem → approach → algorithm → analysis)
  4. Experiments (setup → results → ablation → analysis)
  5. Discussion (interpretation → limitations → future work)
  6. Conclusion (summary → implications → open questions)
- Each section should START with what it will cover
- Each section should END with a transition to the next
- Remove any orphaned paragraphs that don't fit a section
- Add a running example that threads through the paper
""",
    },
    "depth": {
        "threshold": 0.7,
        "mild": """\
DEPTH IMPROVEMENT (minor):
- Expand thin sections with additional technical detail
- Add concrete examples to illustrate abstract concepts
- Include quantitative comparisons where you have qualitative ones
- Deepen the analysis of key results
""",
        "severe": """\
DEPTH IMPROVEMENT (major):
- Current draft is too superficial. For EACH required section:
  * Add at least 2 paragraphs of substantive technical content
  * Include equations, algorithms, or formal definitions where applicable
  * Provide concrete examples with specific numbers
  * Connect to at least 3 specific sources from the reference list
- The Method section must include:
  * Formal problem statement with notation
  * Complete algorithm description (pseudocode if applicable)
  * Complexity analysis (time and space)
  * Theoretical justification or intuition
- The Results section must include:
  * Quantitative comparison tables with baselines
  * Error analysis or failure case discussion
  * Statistical significance testing
""",
    },
    "citations": {
        "threshold": 0.6,
        "mild": """\
CITATION IMPROVEMENT (minor):
- Add 3-5 more citations in the Related Work section
- Ensure every factual claim has a supporting citation
- Replace any [?] or [TODO] citation placeholders
- Verify citation format consistency
""",
        "severe": """\
CITATION IMPROVEMENT (major):
- Current citation coverage is INSUFFICIENT. Required actions:
  1. Every paragraph in Related Work must cite ≥2 papers
  2. Every claim of "prior work shows..." must have a citation
  3. Add seminal/foundational references for the field
  4. Include the most recent (2023-2025) relevant papers
  5. Add at least 2 citations that argue AGAINST your approach
  6. Fix any fabricated or unverifiable citations
  7. Target: ≥15 unique citations for standard, ≥25 for deep
- Citation integration style:
  * Don't just cite — compare: "Unlike [X] who did A, we do B because C"
  * Group related citations: [A; B; C] for shared claims
  * Distinguish: foundational [A], recent [B], and concurrent [C] work
""",
    },
    "style": {
        "threshold": 0.7,
        "mild": """\
STYLE IMPROVEMENT (minor):
- Eliminate first-person pronouns (I/my) — use "we" or passive voice
- Replace informal language with academic equivalents
- Ensure consistent tense (present for facts, past for methods/results)
- Fix any hedging inconsistencies
""",
        "severe": """\
STYLE IMPROVEMENT (major):
- Rewrite for academic register:
  * Replace ALL informal language: "really good" → "significantly improved"
  * Remove conversational fillers: "basically", "actually", "kind of"
  * Use discipline-standard terminology throughout
  * Proper hedging: "demonstrates" vs "suggests" vs "indicates"
- Sentence structure:
  * Vary sentence length (mix short impactful with longer analytical)
  * Topic sentences for every paragraph
  * Parallel structure in lists and comparisons
- Technical precision:
  * Define every technical term on first use
  * Notation consistency across all sections
  * Avoid ambiguous pronouns ("it", "this" without referent)
""",
    },
    "novelty": {
        "threshold": 0.6,
        "mild": """\
NOVELTY IMPROVEMENT (minor):
- Sharpen the novelty claim in the introduction
- Add explicit comparison with the closest related work
- Highlight what SPECIFICALLY is new (not just "we propose")
""",
        "severe": """\
NOVELTY IMPROVEMENT (major):
- The contribution is not clearly differentiated from prior work. Actions:
  1. State the novel contribution in ONE clear sentence in the abstract
  2. In the introduction, add a "Contributions" subsection with numbered items
  3. For each contribution, explain WHY it's novel (not just what it is)
  4. Add a comparison table: Your method vs. closest 3 methods
  5. Explicitly state: "To the best of our knowledge, this is the first..."
  6. Address the most obvious reviewer objection: "One might argue [X], but..."
""",
    },
    "soundness": {
        "threshold": 0.7,
        "mild": """\
SOUNDNESS IMPROVEMENT (minor):
- Add error bars or confidence intervals to all quantitative results
- Verify all equations are dimensionally correct
- Add a sentence on statistical test choice justification
""",
        "severe": """\
SOUNDNESS IMPROVEMENT (major):
- Methodological rigor is insufficient. Required:
  1. Add formal proofs or derivations for all theoretical claims
  2. Include complete experimental details (hyperparams, seeds, hardware)
  3. Add at least 3 ablation experiments
  4. Report statistical significance (p-values or confidence intervals)
  5. Address potential confounds explicitly
  6. Add reproducibility statement: code, data, environment
  7. If making causal claims, justify the identification strategy
""",
    },
    "significance": {
        "threshold": 0.6,
        "mild": """\
SIGNIFICANCE IMPROVEMENT (minor):
- Strengthen the motivation: WHY does this problem matter?
- Add a paragraph on broader impact or practical applications
- Quantify the improvement over prior state of the art
""",
        "severe": """\
SIGNIFICANCE IMPROVEMENT (major):
- The significance of this work is unclear. Actions:
  1. Open with a compelling real-world problem this work addresses
  2. Quantify the impact: "X affects Y million users" or "costs $Z annually"
  3. Explain why existing solutions are insufficient (not just "there's a gap")
  4. Project forward: what becomes possible because of this work?
  5. Add a Broader Impact section (social, economic, environmental)
""",
    },
    "clarity": {
        "threshold": 0.7,
        "mild": """\
CLARITY IMPROVEMENT (minor):
- Simplify the most complex paragraph in each section
- Add a figure or diagram to illustrate the main concept
- Improve the abstract to be self-contained and compelling
""",
        "severe": """\
CLARITY IMPROVEMENT (major):
- Paper is difficult to follow. Required:
  1. Rewrite the abstract: problem → approach → key result → significance (≤250 words)
  2. Add a "method overview" figure showing the pipeline/architecture
  3. Add a notation table if using >5 symbols
  4. Rewrite any paragraph >7 sentences into 2-3 shorter ones
  5. Add running examples throughout the paper
  6. Ensure figure captions are self-contained (understandable without text)
  7. Add one-sentence section summaries at the end of long sections
""",
    },
    "reproducibility": {
        "threshold": 0.6,
        "mild": """\
REPRODUCIBILITY IMPROVEMENT (minor):
- List key hyperparameters and their values
- Mention the computing infrastructure used
- Add a link to code repository (or state "will be released")
""",
        "severe": """\
REPRODUCIBILITY IMPROVEMENT (major):
- Insufficient reproducibility information. Add:
  1. Complete hyperparameter table (ALL model/training hyperparameters)
  2. Hardware: GPU model, CPU, RAM, training time
  3. Software: framework version, key library versions
  4. Data: preprocessing steps, splits, exact dataset versions
  5. Random seeds: report results across ≥3 seeds with std dev
  6. Code availability statement
  7. A "Reproducibility Checklist" in the appendix
""",
    },
    "limitations": {
        "threshold": 0.5,
        "mild": """\
LIMITATIONS IMPROVEMENT (minor):
- Expand the limitations section with 1-2 more specific points
- Connect each limitation to a potential future work direction
""",
        "severe": """\
LIMITATIONS IMPROVEMENT (major):
- A limitations section is REQUIRED. Add the following:
  1. Computational limitations (cost, scalability)
  2. Data limitations (bias, size, domain specificity)
  3. Methodological limitations (assumptions, approximations)
  4. Evaluation limitations (metrics don't capture everything)
  5. Generalizability concerns (what settings won't this work in?)
  6. For EACH limitation: state it honestly, explain its impact,
     and suggest how future work could address it
""",
    },
}

# ---------------------------------------------------------------------------
# Revision Assembly
# ---------------------------------------------------------------------------

REVISION_TEMPLATE = """\
You are revising a research draft based on evaluation feedback.

ORIGINAL DRAFT:
---
{draft}
---

EVALUATION SCORES:
{scores_formatted}

OVERALL DIRECTION:
{overall_direction}

SPECIFIC REVISION INSTRUCTIONS:
{revision_instructions}

RULES:
1. Preserve all content that scored well — do NOT degrade strong sections.
2. Focus revisions on the weakest dimensions.
3. Maintain consistent voice, tense, and style throughout.
4. Every revision should be traceable to a specific instruction above.
5. If adding citations, use [AuthorYear] format as placeholders.
6. The revised draft should be at least as long as the original.

Generate the complete revised draft. Start directly with the first heading.
"""


def get_revision_prompt(
    scores: Dict[str, float],
    draft: str,
    profile=None,
    custom_feedback: str = "",
) -> dict:
    """Assemble a targeted revision prompt based on evaluation scores.

    Args:
        scores: Dimension → score (0-1) dict.
        draft: Current draft text.
        profile: Optional ScenarioProfile.
        custom_feedback: Optional additional feedback text.

    Returns:
        dict with "system", "user" keys.
    """
    # Identify weak dimensions and build instructions
    instructions = []
    weak_dims = []

    for dim, score in sorted(scores.items(), key=lambda x: x[0]):
        if dim not in REVISION_INSTRUCTIONS:
            continue
        config = REVISION_INSTRUCTIONS[dim]
        if score < config["threshold"] * 0.6:
            instructions.append(f"### {dim.upper()} (score: {score:.2f} — CRITICAL)\n{config['severe']}")
            weak_dims.append(dim)
        elif score < config["threshold"]:
            instructions.append(f"### {dim.upper()} (score: {score:.2f} — needs improvement)\n{config['mild']}")
            weak_dims.append(dim)

    if custom_feedback:
        instructions.append(f"### ADDITIONAL FEEDBACK\n{custom_feedback}")

    # Overall direction
    avg_score = sum(scores.values()) / max(len(scores), 1)
    if avg_score < 0.4:
        direction = "Major revision needed. Focus on fundamental improvements to structure, depth, and soundness."
    elif avg_score < 0.6:
        direction = "Moderate revision. Address the critical dimensions below while maintaining existing strengths."
    elif avg_score < 0.8:
        direction = "Minor revision. Polish the weak points and strengthen the narrative."
    else:
        direction = "Near final. Make targeted improvements to reach excellence."

    scores_fmt = "\n".join(f"- {dim}: {score:.2f}" for dim, score in sorted(scores.items()))

    user = REVISION_TEMPLATE.format(
        draft=draft[:6000],
        scores_formatted=scores_fmt,
        overall_direction=direction,
        revision_instructions="\n\n".join(instructions) if instructions else "No specific revision instructions — polish overall quality.",
    )

    system = (
        "You are an expert academic writer revising a research draft. "
        "You make targeted improvements while preserving high-quality existing content. "
        "You never degrade a section that already scores well."
    )

    return {
        "system": system,
        "user": user,
        "weak_dimensions": weak_dims,
    }


def get_revision_dimensions() -> list:
    """List all revision dimensions."""
    return list(REVISION_INSTRUCTIONS.keys())


# ---------------------------------------------------------------------------
# Section-by-Section Refinement (ported from AI-Scientist)
# ---------------------------------------------------------------------------

PER_SECTION_TIPS = {
    "Abstract": """\
- TL;DR of the paper
- What are we trying to do and why is it relevant?
- Why is this hard?
- How do we solve it (our contribution!)
- How do we verify that we solved it (Experiments and results)
- One continuous paragraph, no line breaks.""",

    "Introduction": """\
- Longer version of the Abstract
- What, why, how, and verification
- List contributions as bullet points
- Extra space? Future work!""",

    "Related Work": """\
- Academic siblings: alternative attempts at the same problem
- Compare and contrast, don't just describe
- End each paragraph with how your work differs""",

    "Background": """\
- Academic ancestors: concepts required for understanding the method
- Problem Setting with formal notation
- Highlight unusual assumptions""",

    "Method": """\
- What we do. Why we do it.
- Use the formalism from Problem Setting
- Build on Background concepts""",

    "Experimental Setup": """\
- How we test that our stuff works
- Dataset, evaluation metrics, hyperparameters, implementation details
- Do not imagine unknown hardware details""",

    "Results": """\
- Only results that have actually been run — DO NOT HALLUCINATE
- Compare to baselines with statistics and confidence intervals
- Include ablation studies
- Discuss limitations
- Include all relevant figures""",

    "Conclusion": """\
- Brief recap of the entire paper
- Future work as potential academic offspring""",
}

ERROR_LIST = """\
- Unenclosed math symbols
- Only reference figures that exist in the directory
- LaTeX syntax errors
- Numerical results that do not come from explicit experiments
- Repeatedly defined figure labels
- References to papers not in the .bib file — DO NOT ADD NEW CITATIONS
- Unnecessary verbosity or repetition, unclear text
- Results or insights not yet included
- Relevant figures not yet included in the text
- Unclosed environments (\\begin{figure} without \\end{figure})
- Duplicate headers
- Unescaped symbols (shakespeare_char should be shakespeare\\_char)
"""

REFINEMENT_PROMPT = (
    "Great job! Now criticize and refine only the {section} that you just wrote. "
    "Make this complete in this pass, do not leave any placeholders.\n\n"
    "Pay particular attention to fixing any errors such as:\n" + ERROR_LIST
)

SECOND_REFINEMENT_PROMPT = (
    "Criticize and refine the {section} only. Recall the advice:\n{tips}\n"
    "Make this complete in this pass, do not leave any placeholders.\n\n"
    "Pay attention to how it fits with the rest of the paper.\n"
    "Identify redundancies (repeated figures or text) — decide where to cut.\n"
    "Identify where to save space and be more concise without weakening the message.\n"
    "Fix any remaining errors as before:\n" + ERROR_LIST
)


def get_refinement_prompt(section: str) -> str:
    """Get a first-pass refinement prompt for a section.

    Args:
        section: Section name (e.g. "Introduction", "Method").

    Returns:
        Prompt string for first-pass refinement.
    """
    return REFINEMENT_PROMPT.format(section=section)


def get_second_refinement_prompt(section: str) -> str:
    """Get a second-pass refinement prompt for a section.

    This pass focuses on conciseness, redundancy, and overall fit.

    Args:
        section: Section name (e.g. "Introduction", "Method").

    Returns:
        Prompt string for second-pass refinement.
    """
    tips = PER_SECTION_TIPS.get(section, "")
    return SECOND_REFINEMENT_PROMPT.format(section=section, tips=tips)


def get_section_tips(section: str) -> str:
    """Get writing tips for a section.

    Args:
        section: Section name.

    Returns:
        Tips string, or empty string if section not found.
    """
    return PER_SECTION_TIPS.get(section, "")

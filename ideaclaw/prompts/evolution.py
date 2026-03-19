"""Evolution prompts — idea mutation, crossover, and iterative improvement.

Provides LLM instructions for:
  - 7 mutation types (expand, narrow, pivot, combine, abstract, apply, invert)
  - Crossover between two ideas
  - Fitness-guided evolution
  - Brainstorming from constraints
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

__all__ = ["MUTATION_SYSTEM", "MUTATION_TYPES", "MUTATION_TEMPLATE", "CROSSOVER_SYSTEM", "CROSSOVER_TEMPLATE", "EVOLUTION_SYSTEM", "EVOLUTION_TEMPLATE", "BRAINSTORM_TEMPLATE", "get_mutation_prompt", "get_crossover_prompt", "get_mutation_types"]


MUTATION_SYSTEM = """\
You are a creative research strategist. Your job is to transform research ideas
into stronger, more novel, more impactful variants. You think divergently when
mutating and convergently when refining.
"""

MUTATION_TYPES = {
    "expand": """\
MUTATION TYPE: EXPAND
Take the core idea and expand its scope:
- Apply it to a broader set of problems
- Generalize the methodology to handle more cases
- Increase the scale of ambition
Keep the core insight but make the contribution bigger.
""",
    "narrow": """\
MUTATION TYPE: NARROW
Take the core idea and narrow it to a specific niche:
- Focus on one particular application or domain
- Add constraints that make the problem more tractable
- Target a specific user group or use case
Make it more concrete and achievable.
""",
    "pivot": """\
MUTATION TYPE: PIVOT
Keep the methodology but apply it to a completely different problem:
- Same technique, different domain
- Same insight, different formulation
- Find an unexpected application
The more surprising the pivot, the better.
""",
    "combine": """\
MUTATION TYPE: COMBINE
Merge this idea with a concept from a different field:
- Interdisciplinary combination (e.g., biology + ML)
- Methodological fusion (e.g., statistical + deep learning)
- Application bridging (e.g., NLP technique for computer vision)
The combination should create something genuinely new, not just "A + B."
""",
    "abstract": """\
MUTATION TYPE: ABSTRACT
Extract the abstract principle behind this idea and reformulate:
- What is the underlying pattern or insight?
- Can it be expressed as a general framework?
- Does the abstraction reveal connections to other problems?
Think one level above the specific implementation.
""",
    "apply": """\
MUTATION TYPE: APPLY (Practical)
Make this idea maximally practical and deployable:
- How would this work in a real production system?
- What engineering challenges need solving?
- What's the minimum viable version?
- Who would pay for this? What's the business case?
""",
    "invert": """\
MUTATION TYPE: INVERT
Take the opposite approach or challenge the core assumption:
- What if the key assumption is wrong?
- What if you solved the inverse problem instead?
- What if the constraint is actually a feature?
- Contrarian thinking often leads to breakthroughs.
""",
}

MUTATION_TEMPLATE = """\
{mutation_type_instruction}

ORIGINAL IDEA:
{idea}

DOMAIN: {domain}

{context}

Generate {n_variants} distinct variant(s) of this idea.

For each variant:
1. **Variant Title**: A compelling, specific title
2. **Core Change**: What you changed and why (1-2 sentences)
3. **Description**: Full description of the mutated idea (3-5 sentences)
4. **Novelty Argument**: Why this variant is interesting/novel
5. **Feasibility**: How hard to execute [Easy/Medium/Hard]
6. **Risk**: What could go wrong

Number each variant clearly.
"""

CROSSOVER_SYSTEM = """\
You are a research synthesis expert. You combine the strongest elements of
two different research ideas into a hybrid that's better than either parent.
"""

CROSSOVER_TEMPLATE = """\
PARENT IDEA A:
{idea_a}
(Score: {score_a})

PARENT IDEA B:
{idea_b}
(Score: {score_b})

Create a HYBRID idea that combines the best elements of both parents.
The hybrid should:
1. Inherit the strongest methodological element from each parent
2. Address a weakness of each parent using strength from the other
3. Be more than just "A + B" — find genuine synergy
4. Be feasible to execute

Format:
1. **Hybrid Title**: [title]
2. **From Parent A**: [what's inherited]
3. **From Parent B**: [what's inherited]
4. **Novel Synergy**: [what's new from the combination]
5. **Full Description**: [3-5 sentences]
6. **Expected Advantage**: [why this beats both parents]
"""

EVOLUTION_SYSTEM = """\
You are running a research idea evolution process.
Given a population of ideas with fitness scores, you select the best,
mutate them, and produce the next generation.
"""

EVOLUTION_TEMPLATE = """\
CURRENT GENERATION (ranked by fitness):
{population}

GENERATION: {generation} / {max_generations}

SELECTION PRESSURE: {pressure}

Based on the fitness scores:
1. SELECT the top ideas (highest scores)
2. MUTATE each selected idea to create variants
3. CROSSOVER the best pair to create a hybrid
4. Produce {n_offspring} offspring ideas for the next generation

For each offspring, provide:
- **Title**: [title]
- **Parent(s)**: [which parent(s) and mutation type]
- **Description**: [3-5 sentences]
- **Expected Fitness Improvement**: [why this should score higher]
"""

BRAINSTORM_TEMPLATE = """\
Generate {n_ideas} research ideas given these constraints:

DOMAIN: {domain}
CONSTRAINTS:
{constraints}

DESIRED PROPERTIES:
- Novel (not already well-explored)
- Feasible (can be done with available resources)
- Impactful (addresses an important problem)
- Timely (relevant to current trends)

For each idea:
1. **Title**: Specific, compelling
2. **Problem**: What problem does this solve?
3. **Approach**: High-level methodology (2-3 sentences)
4. **Novelty**: Why hasn't this been done?
5. **Impact**: Who benefits and how?
6. **Difficulty**: [Easy/Medium/Hard]
"""


def get_mutation_prompt(
    idea: str,
    mutation_type: str = "expand",
    domain: str = "general",
    n_variants: int = 3,
    context: str = "",
) -> dict:
    """Get a mutation prompt for a specific mutation type."""
    mt_instruction = MUTATION_TYPES.get(mutation_type, MUTATION_TYPES["expand"])
    return {
        "system": MUTATION_SYSTEM,
        "user": MUTATION_TEMPLATE.format(
            mutation_type_instruction=mt_instruction,
            idea=idea,
            domain=domain,
            n_variants=n_variants,
            context=context or "(No additional context.)",
        ),
    }


def get_crossover_prompt(
    idea_a: str, idea_b: str,
    score_a: float = 0.0, score_b: float = 0.0,
) -> dict:
    """Get a crossover prompt combining two ideas."""
    return {
        "system": CROSSOVER_SYSTEM,
        "user": CROSSOVER_TEMPLATE.format(
            idea_a=idea_a, idea_b=idea_b,
            score_a=f"{score_a:.2f}", score_b=f"{score_b:.2f}",
        ),
    }


def get_mutation_types() -> list:
    """List all available mutation types."""
    return list(MUTATION_TYPES.keys())

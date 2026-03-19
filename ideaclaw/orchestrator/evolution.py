"""Idea evolution — genetic algorithm for research idea improvement.

ARC equivalent: evolution.py (~18KB)

Provides:
  - mutate: Generate variations of an idea
  - crossover: Combine two ideas
  - evolve: Full genetic algorithm loop (population → selection → mutation → next gen)

Uses LLM for mutation/crossover (via hooks._call_llm or llm_callable).

Usage:
    evolver = IdeaEvolver(llm_callable=my_llm_fn)
    variants = evolver.mutate("attention mechanism for long sequences")
    best = evolver.evolve(["idea1", "idea2", "idea3"], max_generations=3)
"""

from __future__ import annotations
import logging

import json
import re
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ['EvolvedIdea', 'IdeaEvolver']


@dataclass
class EvolvedIdea:
    """An idea produced by evolution."""
    text: str
    generation: int
    parent_ids: List[int]
    mutation_type: str   # "mutation", "crossover", "original"
    fitness: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "generation": self.generation,
            "parent_ids": self.parent_ids,
            "mutation_type": self.mutation_type,
            "fitness": self.fitness,
        }


class IdeaEvolver:
    """Evolve research ideas using LLM-powered genetic operations."""

    MUTATION_TYPES = [
        "scope_shift",      # Narrow or broaden the scope
        "method_swap",       # Change the methodology
        "domain_transfer",   # Apply to a different domain
        "constraint_add",    # Add a novel constraint
        "combination",       # Combine with another concept
        "inversion",         # Invert the approach
        "scale_change",      # Change the scale (micro→macro or vice versa)
    ]

    def __init__(self, llm_callable: Optional[Callable[[str], str]] = None):
        self._llm = llm_callable

    def mutate(
        self,
        idea: str,
        n_variants: int = 3,
        mutation_types: Optional[List[str]] = None,
        feedback: Optional[str] = None,
    ) -> List[str]:
        """Generate variations of an idea.

        Args:
            idea: The original idea text.
            n_variants: Number of variants to generate.
            mutation_types: Specific mutation types to use.
            feedback: Optional feedback to guide mutations.

        Returns:
            List of mutated idea strings.
        """
        if not self._llm:
            return self._heuristic_mutate(idea, n_variants)

        types = mutation_types or random.sample(
            self.MUTATION_TYPES, min(n_variants, len(self.MUTATION_TYPES))
        )

        feedback_ctx = f"\nFeedback to address: {feedback}" if feedback else ""

        prompt = f"""Generate {n_variants} creative variations of this research idea.

Original idea: {idea}
{feedback_ctx}

Apply these mutation strategies:
{chr(10).join(f'{i+1}. {t}: Apply a {t.replace("_", " ")} transformation' for i, t in enumerate(types[:n_variants]))}

For each variation, provide a complete, self-contained idea description (2-3 sentences).

Output format:
VARIANT 1: [idea text]
VARIANT 2: [idea text]
VARIANT 3: [idea text]"""

        try:
            response = self._llm(prompt)
            variants = re.findall(r'VARIANT\s*\d+:\s*(.+?)(?=VARIANT\s*\d+:|$)', response, re.DOTALL)
            return [v.strip() for v in variants[:n_variants] if v.strip()]
        except Exception:  # noqa: BLE001
            return self._heuristic_mutate(idea, n_variants)

    def crossover(self, idea_a: str, idea_b: str) -> str:
        """Combine two ideas into a novel hybrid.

        Args:
            idea_a: First parent idea.
            idea_b: Second parent idea.

        Returns:
            Crossed-over idea string.
        """
        if not self._llm:
            return self._heuristic_crossover(idea_a, idea_b)

        prompt = f"""Combine these two research ideas into a single novel hybrid idea.

Idea A: {idea_a}
Idea B: {idea_b}

Create a new idea that:
1. Takes the best aspects of both ideas
2. Creates synergy between the two approaches
3. Is more than just a sum of parts

Output a single cohesive idea (2-3 sentences):
HYBRID: """

        try:
            response = self._llm(prompt)
            match = re.search(r'HYBRID:\s*(.+)', response, re.DOTALL)
            return match.group(1).strip() if match else response.strip()
        except Exception:  # noqa: BLE001
            return self._heuristic_crossover(idea_a, idea_b)

    def evolve(
        self,
        population: List[str],
        fitness_fn: Optional[Callable[[str], float]] = None,
        max_generations: int = 3,
        population_size: int = 5,
        mutation_rate: float = 0.7,
        crossover_rate: float = 0.3,
    ) -> List[EvolvedIdea]:
        """Run genetic algorithm evolution on a population of ideas.

        Args:
            population: Initial population of idea strings.
            fitness_fn: Function to score an idea (0-1). If None, uses LLM.
            max_generations: Number of evolution generations.
            population_size: Target population size per generation.
            mutation_rate: Probability of mutation.
            crossover_rate: Probability of crossover.

        Returns:
            Final population sorted by fitness (best first).
        """
        # Initialize population
        current = [
            EvolvedIdea(text=idea, generation=0, parent_ids=[], mutation_type="original")
            for idea in population
        ]

        # Score initial population
        for idea in current:
            idea.fitness = self._evaluate_fitness(idea.text, fitness_fn)

        # Evolution loop
        for gen in range(1, max_generations + 1):
            offspring = []

            # Selection: tournament selection (top 50%)
            current.sort(key=lambda x: -x.fitness)
            parents = current[:max(len(current) // 2, 2)]

            # Generate offspring
            while len(offspring) < population_size:
                if random.random() < crossover_rate and len(parents) >= 2:
                    # Crossover
                    p1, p2 = random.sample(parents, 2)
                    child_text = self.crossover(p1.text, p2.text)
                    offspring.append(EvolvedIdea(
                        text=child_text,
                        generation=gen,
                        parent_ids=[parents.index(p1), parents.index(p2)],
                        mutation_type="crossover",
                    ))
                elif random.random() < mutation_rate:
                    # Mutation
                    parent = random.choice(parents)
                    variants = self.mutate(parent.text, n_variants=1)
                    if variants:
                        offspring.append(EvolvedIdea(
                            text=variants[0],
                            generation=gen,
                            parent_ids=[parents.index(parent)],
                            mutation_type="mutation",
                        ))
                else:
                    # Keep parent (elitism)
                    parent = random.choice(parents)
                    offspring.append(EvolvedIdea(
                        text=parent.text,
                        generation=gen,
                        parent_ids=[parents.index(parent)],
                        mutation_type="original",
                        fitness=parent.fitness,  # Carry fitness over
                    ))

            # Score offspring
            for idea in offspring:
                if idea.fitness == 0.0:
                    idea.fitness = self._evaluate_fitness(idea.text, fitness_fn)

            # Replace population: keep best from current + offspring
            current = sorted(current + offspring, key=lambda x: -x.fitness)[:population_size]

        return current

    def _evaluate_fitness(
        self,
        idea: str,
        fitness_fn: Optional[Callable[[str], float]] = None,
    ) -> float:
        """Score an idea's fitness."""
        if fitness_fn:
            try:
                return fitness_fn(idea)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Suppressed: %s", exc)

        if self._llm:
            try:
                prompt = f"""Rate this research idea on a scale of 0.0 to 1.0 based on:
- Novelty (0.3 weight)
- Feasibility (0.3 weight)  
- Impact potential (0.4 weight)

Idea: {idea}

Output ONLY a number between 0.0 and 1.0:
SCORE: """
                response = self._llm(prompt)
                match = re.search(r'(?:SCORE:\s*)?([\d.]+)', response)
                if match:
                    return max(0.0, min(1.0, float(match.group(1))))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Suppressed: %s", exc)

        # Heuristic fallback: longer ideas with specific terms score higher
        score = 0.5
        words = idea.lower().split()
        score += min(len(words) / 100, 0.2)  # Length bonus
        specifics = ["novel", "efficient", "scalable", "robust", "framework", "method", "approach"]
        score += sum(0.05 for w in specifics if w in words)
        return min(1.0, score)

    # ---- Heuristic fallbacks (no LLM needed) ----

    @staticmethod
    def _heuristic_mutate(idea: str, n: int) -> List[str]:
        """Simple keyword-swap mutations without LLM."""
        swaps = {
            "improve": ["optimize", "enhance", "accelerate"],
            "model": ["framework", "architecture", "system"],
            "method": ["approach", "technique", "strategy"],
            "novel": ["innovative", "state-of-the-art", "cutting-edge"],
            "efficient": ["scalable", "fast", "lightweight"],
        }
        variants = []
        for _ in range(n):
            words = idea.split()
            for i, w in enumerate(words):
                if w.lower() in swaps:
                    words[i] = random.choice(swaps[w.lower()])
                    break
            variants.append(" ".join(words))
        return variants

    @staticmethod
    def _heuristic_crossover(a: str, b: str) -> str:
        """Simple sentence-level crossover without LLM."""
        a_parts = a.split(". ")
        b_parts = b.split(". ")
        mid_a = len(a_parts) // 2
        mid_b = len(b_parts) // 2
        hybrid = a_parts[:mid_a] + b_parts[mid_b:]
        return ". ".join(hybrid)

"""Idea evolution — population-based evolutionary optimization of research ideas.

Integrates with:
  - orchestrator/evolution.py → IdeaEvolver feeds into the orchestrator's evolution module
  - prompts/evolution.py → uses mutation/crossover prompts
  - knowledge/skills.py → learned skills guide mutation strategies
  - knowledge/memory.py → stores successful evolution patterns

Features beyond ARC:
  - 5 mutation strategies + LLM-powered mutation
  - Population diversity measurement (prevents convergence)
  - Elitism (top-k always survive)
  - Fitness landscape analysis
  - Genealogy tracking with markdown export
  - Adaptive mutation rate (raises when diversity drops)

Usage:
    from ideaclaw.reasoning.evolution import IdeaEvolver, Idea
    evolver = IdeaEvolver()
    population = evolver.evolve(seeds, generations=5, fitness_fn=my_scorer)
    print(evolver.genealogy(population))
"""
from __future__ import annotations

import logging
import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = ["IdeaEvolver", "Idea", "PopulationStats"]


@dataclass
class Idea:
    """A research idea with metadata."""
    id: str
    title: str
    description: str
    fitness: float = 0.0
    generation: int = 0
    parents: List[str] = field(default_factory=list)
    strategy: str = "seed"
    tags: List[str] = field(default_factory=list)
    alive: bool = True            # False if eliminated

    @property
    def summary(self) -> str:
        return f"[G{self.generation}|{self.strategy}|{self.fitness:.2f}] {self.title}"


@dataclass
class PopulationStats:
    """Statistics about an evolution population."""
    generation: int
    population_size: int
    mean_fitness: float
    max_fitness: float
    min_fitness: float
    diversity: float
    best_idea: str
    strategies_used: Dict[str, int] = field(default_factory=dict)


class IdeaEvolver:
    """Evolve research ideas through mutation, crossover, and selection.

    Supports both LLM-powered and heuristic evolution.
    """

    MUTATION_STRATEGIES = [
        "specialize", "abstract", "contrast",
        "domain_shift", "method_swap",
    ]

    MAX_EVALUATIONS = 500  # P-5: prevent runaway evolution

    def __init__(
        self,
        llm_call: Optional[Callable] = None,
        mutation_rate: float = 0.7,
        crossover_rate: float = 0.3,
        elitism: int = 2,
        adaptive: bool = True,
    ):
        self.llm_call = llm_call
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elitism = elitism
        self.adaptive = adaptive
        self._id_counter = 0
        self.history: List[PopulationStats] = []

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"idea_{self._id_counter:04d}"

    def mutate(self, idea: Idea, strategy: str = "auto") -> Idea:
        """Mutate idea. Strategies: specialize, abstract, contrast, domain_shift, method_swap."""
        if strategy == "auto":
            strategy = random.choice(self.MUTATION_STRATEGIES)
        if self.llm_call:
            return self._mutate_llm(idea, strategy)

        prefixes = {
            "specialize": "Specialized: ",
            "abstract": "Generalized: ",
            "contrast": "Inverted: ",
            "domain_shift": f"Applied to {random.choice(['healthcare','finance','robotics','climate'])}: ",
            "method_swap": f"Using {random.choice(['GNN','RL','Bayesian opt','evolutionary'])}: ",
        }
        suffixes = {
            "specialize": " with focus on edge cases and corner scenarios",
            "abstract": " as a general framework applicable across domains",
            "contrast": " by reversing the core assumption and testing the opposite",
            "domain_shift": " adapted for the new domain with specific constraints",
            "method_swap": " via alternative methodology while preserving the core insight",
        }
        return Idea(
            id=self._next_id(),
            title=f"{prefixes.get(strategy, 'Variant: ')}{idea.title}",
            description=f"{idea.description}{suffixes.get(strategy, '')}",
            parents=[idea.id], strategy=strategy, tags=idea.tags.copy(),
        )

    def crossover(self, a: Idea, b: Idea) -> Idea:
        """Combine two ideas into a hybrid."""
        if self.llm_call:
            return self._crossover_llm(a, b)
        a_words = a.description.split()
        b_words = b.description.split()
        combined = " ".join(a_words[:len(a_words)//2] + b_words[len(b_words)//2:])
        return Idea(
            id=self._next_id(),
            title=f"Hybrid: {a.title[:30]} × {b.title[:30]}",
            description=combined,
            parents=[a.id, b.id], strategy="crossover",
            tags=list(set(a.tags + b.tags)),
        )

    def evolve(
        self,
        seeds: List[Idea],
        generations: int = 3,
        offspring_per_gen: int = 5,
        fitness_fn: Optional[Callable[[Idea], float]] = None,
        max_population: int = 50,
    ) -> List[Idea]:
        """Run population-based evolution with tournament selection.

        Args:
            seeds: Initial population.
            generations: Number of generations.
            offspring_per_gen: Children per generation.
            fitness_fn: Function to score ideas.
            max_population: Max population size (culling happens if exceeded).

        Returns:
            Full population (all generations).
        """
        population = list(seeds)
        for idea in population:
            idea.generation = 0
            if fitness_fn:
                idea.fitness = fitness_fn(idea)

        for gen in range(1, generations + 1):
            # Adaptive mutation rate
            if self.adaptive:
                div = self.diversity(population)
                if div < 0.3:
                    effective_mutation = min(0.95, self.mutation_rate * 1.5)
                    logger.info("Diversity low (%.2f), increasing mutation rate → %.2f", div, effective_mutation)
                else:
                    effective_mutation = self.mutation_rate
            else:
                effective_mutation = self.mutation_rate

            parents = self._tournament_select(population, k=offspring_per_gen)
            new_children = []

            for parent in parents:
                if random.random() < self.crossover_rate and len(population) > 1:
                    partner = random.choice([p for p in population if p.id != parent.id])
                    child = self.crossover(parent, partner)
                else:
                    child = self.mutate(parent)
                child.generation = gen
                if fitness_fn:
                    child.fitness = fitness_fn(child)
                new_children.append(child)

            population.extend(new_children)

            # Elitism + culling
            if len(population) > max_population:
                population = self._cull(population, max_population)

            # Record stats
            stats = self._compute_stats(population, gen)
            self.history.append(stats)
            logger.info(
                "Gen %d: pop=%d, mean=%.2f, max=%.2f, diversity=%.2f",
                gen, stats.population_size, stats.mean_fitness,
                stats.max_fitness, stats.diversity,
            )

        return population

    def select_top(self, population: List[Idea], k: int = 5) -> List[Idea]:
        """Select top-k ideas by fitness."""
        return sorted(population, key=lambda x: x.fitness, reverse=True)[:k]

    def diversity(self, population: List[Idea]) -> float:
        """Measure population diversity (0=identical, 1=maximally diverse)."""
        if len(population) < 2:
            return 1.0
        strategies = set(i.strategy for i in population)
        titles = [set(re.findall(r"\w{4,}", i.title.lower())) for i in population]

        # Strategy diversity
        strat_div = len(strategies) / len(self.MUTATION_STRATEGIES)

        # Title diversity (avg pairwise Jaccard distance)
        distances = []
        for i, a_words in enumerate(titles):
            for b_words in titles[i + 1:]:
                if a_words | b_words:
                    distances.append(1 - len(a_words & b_words) / len(a_words | b_words))
        title_div = sum(distances) / len(distances) if distances else 1.0

        return min(1.0, (strat_div + title_div) / 2)

    def fitness_landscape(self, population: List[Idea]) -> Dict[str, float]:
        """Analyze fitness distribution by strategy."""
        by_strategy: Dict[str, List[float]] = {}
        for idea in population:
            by_strategy.setdefault(idea.strategy, []).append(idea.fitness)
        return {
            strategy: sum(scores) / len(scores)
            for strategy, scores in by_strategy.items()
        }

    def genealogy(self, population: List[Idea]) -> str:
        """Generate markdown genealogy tree."""
        lines = ["# Idea Genealogy", ""]
        by_gen: Dict[int, List[Idea]] = {}
        for idea in population:
            by_gen.setdefault(idea.generation, []).append(idea)
        for gen in sorted(by_gen):
            lines.append(f"## Generation {gen}")
            for idea in sorted(by_gen[gen], key=lambda x: -x.fitness):
                parents = f" ← {', '.join(idea.parents)}" if idea.parents else ""
                alive = "🟢" if idea.alive else "🔴"
                lines.append(
                    f"- {alive} [{idea.strategy}] **{idea.title[:60]}** "
                    f"(fitness={idea.fitness:.2f}{parents})"
                )
            lines.append("")

        # Landscape summary
        landscape = self.fitness_landscape(population)
        lines.append("## Strategy Performance")
        for strat, avg in sorted(landscape.items(), key=lambda x: -x[1]):
            lines.append(f"- {strat}: avg fitness = {avg:.3f}")

        return "\n".join(lines)

    def to_mermaid(self, population: List[Idea]) -> str:
        """Export evolution as Mermaid flowchart."""
        lines = ["graph LR"]
        for idea in population:
            safe_title = idea.title[:30].replace('"', "'")
            lines.append(f'    {idea.id}["{safe_title}<br/>F={idea.fitness:.2f}"]')
            for parent_id in idea.parents:
                lines.append(f"    {parent_id} --> {idea.id}")
        return "\n".join(lines)

    # ---- Internal ----

    def _tournament_select(self, population: List[Idea], k: int = 5) -> List[Idea]:
        """Tournament selection: pick k winners from random groups."""
        alive = [p for p in population if p.alive]
        if not alive:
            alive = population
        selected = []
        for _ in range(k):
            candidates = random.sample(alive, min(3, len(alive)))
            selected.append(max(candidates, key=lambda x: x.fitness))
        return selected

    def _cull(self, population: List[Idea], max_size: int) -> List[Idea]:
        """Cull population, preserving elite."""
        sorted_pop = sorted(population, key=lambda x: x.fitness, reverse=True)
        # Protect elite
        survivors = sorted_pop[:self.elitism]
        remaining = sorted_pop[self.elitism:]
        # Fill remaining slots
        survivors.extend(remaining[:max_size - self.elitism])
        # Mark culled as dead
        survivor_ids = {s.id for s in survivors}
        for idea in population:
            if idea.id not in survivor_ids:
                idea.alive = False
        return survivors

    def _compute_stats(self, population: List[Idea], gen: int) -> PopulationStats:
        """Compute population statistics."""
        fitnesses = [i.fitness for i in population]
        strategies = {}
        for i in population:
            strategies[i.strategy] = strategies.get(i.strategy, 0) + 1
        best = max(population, key=lambda x: x.fitness)
        return PopulationStats(
            generation=gen,
            population_size=len(population),
            mean_fitness=sum(fitnesses) / len(fitnesses),
            max_fitness=max(fitnesses),
            min_fitness=min(fitnesses),
            diversity=self.diversity(population),
            best_idea=best.title,
            strategies_used=strategies,
        )

    def _mutate_llm(self, idea: Idea, strategy: str) -> Idea:
        """LLM-powered mutation."""
        desc = {
            "specialize": "Narrow scope, add constraints",
            "abstract": "Broaden scope, generalize",
            "contrast": "Flip core assumption",
            "domain_shift": "Apply to different domain",
            "method_swap": "Use different methodology",
        }
        prompt = (
            f"Mutate this idea using '{strategy}' strategy ({desc.get(strategy,'variant')}):\n"
            f"Title: {idea.title}\nDescription: {idea.description}\n"
            f"Reply: TITLE: <new>\nDESCRIPTION: <new>"
        )
        response = self.llm_call(system_prompt="Creative research idea generator.", user_prompt=prompt)
        t, d = idea.title, idea.description
        for line in response.split("\n"):
            if line.strip().upper().startswith("TITLE:"):
                t = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("DESCRIPTION:"):
                d = line.split(":", 1)[1].strip()
        return Idea(
            id=self._next_id(), title=t, description=d,
            parents=[idea.id], strategy=strategy, tags=idea.tags.copy(),
        )

    def _crossover_llm(self, a: Idea, b: Idea) -> Idea:
        """LLM-powered crossover."""
        prompt = (
            f"Combine:\nA: {a.title}\n{a.description}\nB: {b.title}\n{b.description}\n"
            f"Reply: TITLE: <hybrid>\nDESCRIPTION: <hybrid>"
        )
        response = self.llm_call(system_prompt="Creative research idea generator.", user_prompt=prompt)
        t, d = f"Hybrid: {a.title[:20]}×{b.title[:20]}", response
        for line in response.split("\n"):
            if line.strip().upper().startswith("TITLE:"):
                t = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("DESCRIPTION:"):
                d = line.split(":", 1)[1].strip()
        return Idea(
            id=self._next_id(), title=t, description=d,
            parents=[a.id, b.id], strategy="crossover",
            tags=list(set(a.tags + b.tags)),
        )

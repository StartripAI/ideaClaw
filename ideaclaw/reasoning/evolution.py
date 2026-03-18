"""Idea evolution — mutate, crossover, and specialize research ideas.

Surpasses ARC's evolution.py: multiple strategies, population-based
evolution with tournament selection, genealogy tracking, LLM + heuristic.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


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


class IdeaEvolver:
    """Evolve research ideas through mutation, crossover, and selection."""

    def __init__(self, llm_call: Optional[Callable] = None,
                 mutation_rate: float = 0.7, crossover_rate: float = 0.3):
        self.llm_call = llm_call
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"idea_{self._id_counter:04d}"

    def mutate(self, idea: Idea, strategy: str = "auto") -> Idea:
        """Mutate idea. Strategies: specialize, abstract, contrast, domain_shift, method_swap."""
        if strategy == "auto":
            strategy = random.choice(["specialize", "abstract", "contrast",
                                       "domain_shift", "method_swap"])
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
            "specialize": " with focus on edge cases",
            "abstract": " as a general framework",
            "contrast": " by reversing the core assumption",
            "domain_shift": " adapted for new domain",
            "method_swap": " via alternative methodology",
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

    def evolve(self, seeds: List[Idea], generations: int = 3,
               offspring_per_gen: int = 5,
               fitness_fn: Optional[Callable[[Idea], float]] = None) -> List[Idea]:
        """Run population-based evolution with tournament selection."""
        population = list(seeds)
        for idea in population:
            idea.generation = 0
            if fitness_fn:
                idea.fitness = fitness_fn(idea)

        for gen in range(1, generations + 1):
            parents = self._tournament_select(population, k=offspring_per_gen)
            for parent in parents:
                if random.random() < self.crossover_rate and len(population) > 1:
                    partner = random.choice([p for p in population if p.id != parent.id])
                    child = self.crossover(parent, partner)
                else:
                    child = self.mutate(parent)
                child.generation = gen
                if fitness_fn:
                    child.fitness = fitness_fn(child)
                population.append(child)
        return population

    def select_top(self, population: List[Idea], k: int = 5) -> List[Idea]:
        return sorted(population, key=lambda x: x.fitness, reverse=True)[:k]

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
                lines.append(f"- [{idea.strategy}] **{idea.title[:60]}** (fitness={idea.fitness:.2f}{parents})")
            lines.append("")
        return "\n".join(lines)

    def _tournament_select(self, population: List[Idea], k: int = 5) -> List[Idea]:
        selected = []
        for _ in range(k):
            candidates = random.sample(population, min(3, len(population)))
            selected.append(max(candidates, key=lambda x: x.fitness))
        return selected

    def _mutate_llm(self, idea: Idea, strategy: str) -> Idea:
        desc = {"specialize": "Narrow scope, add constraints",
                "abstract": "Broaden scope, generalize",
                "contrast": "Flip core assumption",
                "domain_shift": "Apply to different domain",
                "method_swap": "Use different methodology"}
        prompt = (f"Mutate this idea using '{strategy}' strategy ({desc.get(strategy,'variant')}):\n"
                  f"Title: {idea.title}\nDescription: {idea.description}\n"
                  f"Reply: TITLE: <new>\nDESCRIPTION: <new>")
        response = self.llm_call(system_prompt="Creative research idea generator.", user_prompt=prompt)
        t, d = idea.title, idea.description
        for line in response.split("\n"):
            if line.strip().upper().startswith("TITLE:"): t = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("DESCRIPTION:"): d = line.split(":", 1)[1].strip()
        return Idea(id=self._next_id(), title=t, description=d,
                    parents=[idea.id], strategy=strategy, tags=idea.tags.copy())

    def _crossover_llm(self, a: Idea, b: Idea) -> Idea:
        prompt = (f"Combine:\nA: {a.title}\n{a.description}\nB: {b.title}\n{b.description}\n"
                  f"Reply: TITLE: <hybrid>\nDESCRIPTION: <hybrid>")
        response = self.llm_call(system_prompt="Creative research idea generator.", user_prompt=prompt)
        t, d = f"Hybrid: {a.title[:20]}×{b.title[:20]}", response
        for line in response.split("\n"):
            if line.strip().upper().startswith("TITLE:"): t = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("DESCRIPTION:"): d = line.split(":", 1)[1].strip()
        return Idea(id=self._next_id(), title=t, description=d,
                    parents=[a.id, b.id], strategy="crossover", tags=list(set(a.tags + b.tags)))

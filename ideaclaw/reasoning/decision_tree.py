"""Decision tree analysis — structured decision-making with uncertainty propagation.

Integrates with:
  - reasoning.decompose → decomposes decisions into sub-decisions
  - reasoning.synthesize → uses evidence to evaluate branches
  - orchestrator.loop → used in idea evaluation stages

Features:
  - Decision tree construction from criteria
  - Uncertainty propagation through branches
  - Expected value computation
  - Sensitivity analysis
  - Mermaid diagram export
  - Pruning of dominated branches

Usage:
    from ideaclaw.reasoning.decision_tree import DecisionTree, Node
    tree = DecisionTree("Should we pursue X?")
    tree.add_option("Approach A", criteria={"feasibility": 0.8, "impact": 0.6})
    tree.add_option("Approach B", criteria={"feasibility": 0.5, "impact": 0.9})
    best = tree.evaluate()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["DecisionTree", "DecisionNode", "DecisionResult"]


@dataclass
class DecisionNode:
    """A node in the decision tree."""
    label: str
    criteria: Dict[str, float] = field(default_factory=dict)   # criterion → score (0-1)
    probability: float = 1.0       # probability of this branch
    children: List["DecisionNode"] = field(default_factory=list)
    is_leaf: bool = True
    notes: str = ""

    @property
    def expected_value(self) -> float:
        """Compute expected value: mean of criteria × probability."""
        if not self.criteria:
            return 0.0
        return (sum(self.criteria.values()) / len(self.criteria)) * self.probability

    @property
    def weighted_score(self) -> float:
        """Score weighted by number of criteria met above threshold."""
        threshold = 0.5
        above = sum(1 for v in self.criteria.values() if v >= threshold)
        return above / max(len(self.criteria), 1)


@dataclass
class DecisionResult:
    """Result of decision tree evaluation."""
    best_option: str
    best_score: float
    ranking: List[Tuple[str, float]]
    sensitivity: Dict[str, Dict[str, float]]
    dominated: List[str]
    reasoning: str


class DecisionTree:
    """Decision tree for structured multi-criteria analysis.

    Supports:
    - Multi-criteria evaluation with customizable weights
    - Uncertainty propagation via branch probabilities
    - Sensitivity analysis (how much does changing each criterion matter?)
    - Dominance pruning (removing options that are worse in ALL criteria)
    - Mermaid diagram export for visualization
    """

    DEFAULT_WEIGHTS = {
        "feasibility": 1.0,
        "impact": 1.2,
        "novelty": 1.0,
        "risk": 0.8,
        "cost": 0.7,
        "timeline": 0.6,
    }

    def __init__(
        self,
        question: str,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.question = question
        self.weights = weights or dict(self.DEFAULT_WEIGHTS)
        self.root = DecisionNode(label=question, is_leaf=False)
        self.options: List[DecisionNode] = []

    def add_option(
        self,
        label: str,
        criteria: Optional[Dict[str, float]] = None,
        probability: float = 1.0,
        notes: str = "",
    ) -> DecisionNode:
        """Add a decision option (branch)."""
        node = DecisionNode(
            label=label,
            criteria=criteria or {},
            probability=probability,
            notes=notes,
        )
        self.root.children.append(node)
        self.options.append(node)
        logger.debug("Added option '%s' with %d criteria", label, len(criteria or {}))
        return node

    def add_sub_option(
        self,
        parent: DecisionNode,
        label: str,
        criteria: Optional[Dict[str, float]] = None,
        probability: float = 1.0,
    ) -> DecisionNode:
        """Add a sub-option to an existing node."""
        parent.is_leaf = False
        node = DecisionNode(
            label=label, criteria=criteria or {},
            probability=probability,
        )
        parent.children.append(node)
        return node

    def evaluate(self) -> DecisionResult:
        """Evaluate the decision tree and return a recommendation.

        Returns:
            DecisionResult with best option, ranking, sensitivity analysis.
        """
        if not self.options:
            return DecisionResult(
                best_option="(no options)", best_score=0.0,
                ranking=[], sensitivity={}, dominated=[], reasoning="No options to evaluate.",
            )

        # Compute weighted scores
        scores: Dict[str, float] = {}
        for opt in self.options:
            score = self._compute_weighted_score(opt)
            scores[opt.label] = score

        # Ranking
        ranking = sorted(scores.items(), key=lambda x: -x[1])

        # Dominance analysis
        dominated = self._find_dominated()

        # Sensitivity analysis
        sensitivity = self._sensitivity_analysis()

        best = ranking[0]
        reasoning = self._build_reasoning(ranking, dominated, sensitivity)

        result = DecisionResult(
            best_option=best[0], best_score=best[1],
            ranking=ranking, sensitivity=sensitivity,
            dominated=dominated, reasoning=reasoning,
        )

        logger.info("Decision: best='%s' (%.3f), %d dominated", best[0], best[1], len(dominated))
        return result

    def _compute_weighted_score(self, node: DecisionNode) -> float:
        """Compute weighted score for a node."""
        if not node.criteria:
            return 0.0
        total_weight = 0.0
        weighted_sum = 0.0
        for criterion, value in node.criteria.items():
            w = self.weights.get(criterion, 1.0)
            weighted_sum += value * w * node.probability
            total_weight += w
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _find_dominated(self) -> List[str]:
        """Find options that are dominated (worse in ALL criteria)."""
        dominated = []
        for i, a in enumerate(self.options):
            for j, b in enumerate(self.options):
                if i == j:
                    continue
                all_criteria = set(a.criteria.keys()) | set(b.criteria.keys())
                if not all_criteria:
                    continue
                a_worse = all(
                    a.criteria.get(c, 0) <= b.criteria.get(c, 0) for c in all_criteria
                )
                a_strictly_worse = any(
                    a.criteria.get(c, 0) < b.criteria.get(c, 0) for c in all_criteria
                )
                if a_worse and a_strictly_worse:
                    if a.label not in dominated:
                        dominated.append(a.label)
                    break
        return dominated

    def _sensitivity_analysis(self) -> Dict[str, Dict[str, float]]:
        """Sensitivity: how does changing each criteria weight affect scores?"""
        baseline = {opt.label: self._compute_weighted_score(opt) for opt in self.options}
        sensitivity: Dict[str, Dict[str, float]] = {}

        for criterion in self.weights:
            original_weight = self.weights[criterion]

            # Increase weight by 50%
            self.weights[criterion] = original_weight * 1.5
            high_scores = {opt.label: self._compute_weighted_score(opt) for opt in self.options}

            # Decrease weight by 50%
            self.weights[criterion] = original_weight * 0.5
            low_scores = {opt.label: self._compute_weighted_score(opt) for opt in self.options}

            # Restore
            self.weights[criterion] = original_weight

            sensitivity[criterion] = {
                opt.label: high_scores[opt.label] - low_scores[opt.label]
                for opt in self.options
            }

        return sensitivity

    def _build_reasoning(
        self, ranking: List[Tuple[str, float]],
        dominated: List[str], sensitivity: Dict[str, Dict[str, float]],
    ) -> str:
        """Build human-readable reasoning."""
        parts = [f"Decision: {self.question}"]
        parts.append(f"\nBest option: {ranking[0][0]} (score: {ranking[0][1]:.3f})")

        if len(ranking) > 1:
            delta = ranking[0][1] - ranking[1][1]
            if delta > 0.1:
                parts.append(f"  → Clear winner (margin: {delta:.3f})")
            elif delta > 0.02:
                parts.append(f"  → Slight edge (margin: {delta:.3f})")
            else:
                parts.append(f"  → Very close call (margin: {delta:.3f})")

        if dominated:
            parts.append(f"\nDominated (remove from consideration): {', '.join(dominated)}")

        # Most sensitive criteria
        if sensitivity:
            most_sensitive = max(
                sensitivity.items(),
                key=lambda x: max(abs(v) for v in x[1].values()),
            )
            parts.append(f"\nMost sensitive criterion: {most_sensitive[0]}")

        return "\n".join(parts)

    # ---- Visualization ----

    def to_mermaid(self) -> str:
        """Export decision tree as Mermaid diagram."""
        lines = ["graph TD"]
        root_id = "Q"
        lines.append(f'    {root_id}["{self.question}"]')

        for i, opt in enumerate(self.options):
            opt_id = f"O{i}"
            score = self._compute_weighted_score(opt)
            lines.append(f'    {opt_id}["{opt.label}<br/>Score: {score:.2f}"]')
            lines.append(f"    {root_id} --> {opt_id}")

            for j, child in enumerate(opt.children):
                child_id = f"O{i}C{j}"
                child_score = self._compute_weighted_score(child)
                lines.append(f'    {child_id}["{child.label}<br/>{child_score:.2f}"]')
                lines.append(f"    {opt_id} --> {child_id}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the tree for JSON export."""
        def _node_dict(n: DecisionNode) -> Dict[str, Any]:
            return {
                "label": n.label,
                "criteria": n.criteria,
                "probability": n.probability,
                "expected_value": n.expected_value,
                "children": [_node_dict(c) for c in n.children],
            }
        return {
            "question": self.question,
            "weights": self.weights,
            "options": [_node_dict(o) for o in self.options],
        }

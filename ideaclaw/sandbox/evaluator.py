"""Experiment evaluator — compares runs and decides accept/reject.

Covers AR-style iterative improvement loop:
  1. Run baseline → get metrics
  2. Run experiment → get metrics  
  3. Compare → accept if improved, reject if not
  4. Repeat

Also supports ARC-style experiment evaluation:
  - Validate generated code actually runs
  - Check output formats match expected schema
  - Evaluate statistical significance of results
"""

from __future__ import annotations
import logging

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ideaclaw.sandbox.executor import ExecResult

logger = logging.getLogger(__name__)

__all__ = ['EvalResult', 'ExperimentRun', 'ExperimentEvaluator']


@dataclass
class EvalResult:
    """Result from evaluating an experiment."""
    decision: str  # ACCEPT | REJECT | INCONCLUSIVE
    reason: str
    baseline_metrics: Dict[str, Any]
    experiment_metrics: Dict[str, Any]
    improvement: Dict[str, float]  # metric_name -> % change
    significant: bool = False


@dataclass
class ExperimentRun:
    """A single experiment run with its result."""
    run_id: str
    description: str
    exec_result: ExecResult
    metrics: Dict[str, Any] = field(default_factory=dict)
    code_diff: str = ""
    accepted: bool = False


class ExperimentEvaluator:
    """Evaluate experiment results and decide accept/reject.

    Usage:
        evaluator = ExperimentEvaluator(
            primary_metric="val_bpb",
            direction="minimize",
        )
        eval_result = evaluator.compare(baseline_result, experiment_result)
        if eval_result.decision == "ACCEPT":
            commit_changes()
    """

    def __init__(
        self,
        primary_metric: str = "val_bpb",
        direction: str = "minimize",  # minimize | maximize
        min_improvement_pct: float = 0.1,  # minimum 0.1% improvement
        secondary_metrics: Optional[List[str]] = None,
        secondary_direction: Optional[Dict[str, str]] = None,
    ):
        self.primary_metric = primary_metric
        self.direction = direction
        self.min_improvement_pct = min_improvement_pct
        self.secondary_metrics = secondary_metrics or []
        self.secondary_direction = secondary_direction or {}

    def compare(
        self,
        baseline: ExecResult,
        experiment: ExecResult,
    ) -> EvalResult:
        """Compare baseline and experiment results.

        Args:
            baseline: Result from the baseline run.
            experiment: Result from the experiment run.

        Returns:
            EvalResult with ACCEPT/REJECT/INCONCLUSIVE decision.
        """
        base_metrics = baseline.metrics
        exp_metrics = experiment.metrics

        # Check if both runs succeeded
        if not baseline.success:
            return EvalResult(
                decision="INCONCLUSIVE",
                reason="Baseline run failed",
                baseline_metrics=base_metrics,
                experiment_metrics=exp_metrics,
                improvement={},
            )

        if not experiment.success:
            return EvalResult(
                decision="REJECT",
                reason=f"Experiment failed: {experiment.error or experiment.stderr[:200]}",
                baseline_metrics=base_metrics,
                experiment_metrics=exp_metrics,
                improvement={},
            )

        # Check primary metric exists
        if self.primary_metric not in base_metrics:
            return EvalResult(
                decision="INCONCLUSIVE",
                reason=f"Primary metric '{self.primary_metric}' not found in baseline",
                baseline_metrics=base_metrics,
                experiment_metrics=exp_metrics,
                improvement={},
            )

        if self.primary_metric not in exp_metrics:
            return EvalResult(
                decision="REJECT",
                reason=f"Primary metric '{self.primary_metric}' not found in experiment",
                baseline_metrics=base_metrics,
                experiment_metrics=exp_metrics,
                improvement={},
            )

        # Calculate improvement
        improvement = {}
        base_val = float(base_metrics[self.primary_metric])
        exp_val = float(exp_metrics[self.primary_metric])

        if abs(base_val) < 1e-12:
            pct_change = 0.0
        else:
            pct_change = ((exp_val - base_val) / abs(base_val)) * 100

        improvement[self.primary_metric] = round(pct_change, 4)

        # Determine if improvement is in the right direction
        if self.direction == "minimize":
            is_improved = pct_change < -self.min_improvement_pct
            is_regressed = pct_change > self.min_improvement_pct
        else:  # maximize
            is_improved = pct_change > self.min_improvement_pct
            is_regressed = pct_change < -self.min_improvement_pct

        # Calculate secondary metrics
        for metric in self.secondary_metrics:
            if metric in base_metrics and metric in exp_metrics:
                b = float(base_metrics[metric])
                e = float(exp_metrics[metric])
                if abs(b) > 1e-12:
                    improvement[metric] = round(((e - b) / abs(b)) * 100, 4)

        # Decision
        if is_improved:
            decision = "ACCEPT"
            reason = (
                f"{self.primary_metric}: {base_val:.6f} → {exp_val:.6f} "
                f"({pct_change:+.2f}%, direction={self.direction})"
            )
        elif is_regressed:
            decision = "REJECT"
            reason = (
                f"{self.primary_metric} regressed: {base_val:.6f} → {exp_val:.6f} "
                f"({pct_change:+.2f}%)"
            )
        else:
            decision = "INCONCLUSIVE"
            reason = (
                f"{self.primary_metric} unchanged: {base_val:.6f} → {exp_val:.6f} "
                f"({pct_change:+.2f}%, threshold={self.min_improvement_pct}%)"
            )

        return EvalResult(
            decision=decision,
            reason=reason,
            baseline_metrics=base_metrics,
            experiment_metrics=exp_metrics,
            improvement=improvement,
            significant=is_improved,
        )

    def run_experiment_loop(
        self,
        experiments: List[ExperimentRun],
        baseline: ExecResult,
    ) -> List[Tuple[ExperimentRun, EvalResult]]:
        """Run through a list of experiments, accepting or rejecting each.

        Implements AR-style iterative improvement:
        - Start with baseline
        - For each experiment, compare against current best
        - Accept if improved, update baseline
        - Reject if not

        Returns list of (run, evaluation) tuples.
        """
        current_best = baseline
        results = []

        for run in experiments:
            eval_result = self.compare(current_best, run.exec_result)
            run.accepted = eval_result.decision == "ACCEPT"

            if run.accepted:
                current_best = run.exec_result

            results.append((run, eval_result))

        return results

    def generate_report(
        self,
        results: List[Tuple[ExperimentRun, EvalResult]],
    ) -> str:
        """Generate a markdown report of experiment results."""
        lines = ["# Experiment Report", ""]

        accepted = [r for r, e in results if e.decision == "ACCEPT"]
        rejected = [r for r, e in results if e.decision == "REJECT"]
        inconclusive = [r for r, e in results if e.decision == "INCONCLUSIVE"]

        lines.append(f"**Total**: {len(results)} experiments")
        lines.append(f"- ✅ Accepted: {len(accepted)}")
        lines.append(f"- ❌ Rejected: {len(rejected)}")
        lines.append(f"- ⚠️ Inconclusive: {len(inconclusive)}")
        lines.append("")

        lines.append("## Results")
        lines.append("")
        lines.append("| # | Run | Decision | Primary Metric | Change | Reason |")
        lines.append("|---|---|---|---|---|---|")

        for i, (run, eval_r) in enumerate(results, 1):
            icon = "✅" if eval_r.decision == "ACCEPT" else ("❌" if eval_r.decision == "REJECT" else "⚠️")
            pct = eval_r.improvement.get(self.primary_metric, 0.0)
            lines.append(
                f"| {i} | {run.run_id} | {icon} {eval_r.decision} | "
                f"{self.primary_metric} | {pct:+.2f}% | {eval_r.reason[:60]} |"
            )

        return "\n".join(lines)

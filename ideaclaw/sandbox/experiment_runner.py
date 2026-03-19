"""ARC-style experiment runner — the core of AI-Scientist, ported to IdeaClaw.

This is the missing piece: LLM modifies experiment code → sandbox runs it →
collect real results → repeat. Bridges ARC's experiment loop with IdeaClaw's
SandboxExecutor.

ARC flow:
  1. Copy seed experiment (experiment.py + plot.py + baseline run_0)
  2. LLM modifies experiment.py for each new run (via coder/aider)
  3. sandbox runs `python experiment.py --out_dir=run_i`
  4. Collect final_info.json with real metrics
  5. Repeat up to MAX_RUNS times
  6. LLM generates plots via plot.py
  7. LLM writes notes.txt describing results
"""

from __future__ import annotations
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ideaclaw.sandbox.executor import SandboxExecutor, SandboxConfig, ExecResult

logger = logging.getLogger(__name__)

__all__ = ["ExperimentRunner", "ExperimentResult", "ExperimentConfig"]

MAX_RUNS = 5
MAX_ITERS = 4  # max retries per run

# --- Prompts (ported from AI-Scientist) ---

CODER_PROMPT = """\
Your goal is to implement the following idea: {title}.
The proposed experiment is as follows: {idea}.
You are given up to {max_runs} runs to complete the experiments.

Baseline results (run_0):
{baseline_results}

After each change, we will run `python experiment.py --out_dir=run_i`.
YOUR CHANGE MUST USE THIS COMMAND FORMAT.
You can implement the next item on your list after each run.

When you are done with all experiments, respond with "ALL_COMPLETED".
"""

PLOT_PROMPT = """\
Modify `plot.py` to generate the most relevant plots for the writeup.
Fill in the "labels" dictionary with correct names for each run.
Only runs in `labels` will be plotted. Include all relevant runs.
We will run `python plot.py` to generate the plots.
"""

NOTES_PROMPT = """\
Modify `notes.txt` with a description of what each plot shows along with the
filename of the figure. Be in-depth. Someone else will use this to write a report.
"""


@dataclass
class ExperimentConfig:
    """Configuration for an experiment run."""
    max_runs: int = MAX_RUNS
    max_iters_per_run: int = MAX_ITERS
    timeout_seconds: int = 600
    docker_image: str = ""
    gpu_enabled: bool = False
    seed_dir: Optional[str] = None  # Path to seed experiment template


@dataclass
class RunInfo:
    """Info for a single experiment run."""
    run_id: int
    success: bool
    metrics: Dict[str, Any]
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    artifacts: List[str] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """Full experiment result across all runs."""
    title: str
    idea: str
    baseline_metrics: Dict[str, Any]
    runs: List[RunInfo]
    notes: str = ""
    plots: List[str] = field(default_factory=list)
    success: bool = False
    work_dir: str = ""

    @property
    def all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """All run metrics including baseline."""
        result = {"run_0": self.baseline_metrics}
        for r in self.runs:
            result[f"run_{r.run_id}"] = r.metrics
        return result

    @property
    def best_run(self) -> Optional[RunInfo]:
        """Run with best primary metric (lowest loss or highest accuracy)."""
        successful = [r for r in self.runs if r.success and r.metrics]
        if not successful:
            return None
        # Heuristic: if "loss" in metrics, minimize; else maximize first metric
        first_key = list(successful[0].metrics.keys())[0] if successful[0].metrics else None
        if first_key is None:
            return successful[0]
        minimize = "loss" in first_key.lower() or "error" in first_key.lower()
        return min(successful, key=lambda r: r.metrics.get(first_key, float('inf'))) if minimize \
            else max(successful, key=lambda r: r.metrics.get(first_key, float('-inf')))

    def summary_table(self) -> str:
        """Generate a markdown results table."""
        if not self.runs:
            return "No runs completed."
        headers = sorted(set(k for r in self.runs for k in r.metrics))
        if not headers:
            return "No metrics collected."
        lines = ["| Run | " + " | ".join(headers) + " |",
                 "|-----|" + "|".join("---" for _ in headers) + "|"]
        # Baseline
        vals = [str(self.baseline_metrics.get(h, "-")) for h in headers]
        lines.append("| run_0 (baseline) | " + " | ".join(vals) + " |")
        for r in self.runs:
            vals = [str(r.metrics.get(h, "-")) for h in headers]
            lines.append(f"| run_{r.run_id} {'✅' if r.success else '❌'} | " + " | ".join(vals) + " |")
        return "\n".join(lines)


class ExperimentRunner:
    """Runs ARC-style experiments: LLM writes code → sandbox executes → collect results.

    Usage:
        runner = ExperimentRunner(config, llm_fn)
        result = runner.run(title, idea, work_dir)
    """

    def __init__(
        self,
        config: Optional[ExperimentConfig] = None,
        llm_code_fn: Optional[Callable] = None,
    ):
        """
        Args:
            config: Experiment configuration.
            llm_code_fn: Callable(prompt: str, files: dict[str, str]) -> dict[str, str]
                Takes a prompt and current file contents, returns modified file contents.
                This replaces Aider's coder in ARC.
        """
        self.config = config or ExperimentConfig()
        self.llm_code_fn = llm_code_fn
        self.sandbox = SandboxExecutor(SandboxConfig(
            timeout_seconds=self.config.timeout_seconds,
            docker_image=self.config.docker_image,
            gpu_enabled=self.config.gpu_enabled,
        ))

    def run(self, title: str, idea: str, work_dir: Path) -> ExperimentResult:
        """Execute the full experiment loop.

        Args:
            title: Experiment title.
            idea: Description of what to implement.
            work_dir: Directory containing experiment.py, plot.py, and run_0/ baseline.

        Returns:
            ExperimentResult with all run metrics and artifacts.
        """
        work_dir = Path(work_dir)
        result = ExperimentResult(title=title, idea=idea, baseline_metrics={}, runs=[], work_dir=str(work_dir))

        # Step 1: Load baseline results
        baseline_path = work_dir / "run_0" / "final_info.json"
        if baseline_path.exists():
            with open(baseline_path) as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    result.baseline_metrics = {k: v.get("means", v) if isinstance(v, dict) else v for k, v in raw.items()}
        logger.info(f"Baseline: {result.baseline_metrics}")

        # Step 2: Experiment loop
        if self.llm_code_fn is None:
            logger.warning("No LLM code function — running experiment.py as-is")
            for run_id in range(1, self.config.max_runs + 1):
                run_info = self._execute_run(work_dir, run_id)
                result.runs.append(run_info)
                if not run_info.success:
                    break
        else:
            result.runs = self._llm_experiment_loop(title, idea, work_dir, result.baseline_metrics)

        # Step 3: Plotting
        if self.llm_code_fn and any(r.success for r in result.runs):
            self._run_plotting(work_dir, result)

        # Step 4: Notes
        if self.llm_code_fn:
            self._generate_notes(work_dir, result)

        result.success = any(r.success for r in result.runs)
        return result

    def _llm_experiment_loop(self, title: str, idea: str, work_dir: Path,
                              baseline: Dict) -> List[RunInfo]:
        """ARC's core loop: LLM modifies experiment.py → run → collect → repeat."""
        runs = []
        current_iter = 0
        run_id = 1

        # Initial prompt
        prompt = CODER_PROMPT.format(
            title=title, idea=idea,
            max_runs=self.config.max_runs,
            baseline_results=json.dumps(baseline, indent=2),
        )

        # Read current files
        exp_file = work_dir / "experiment.py"
        files = {"experiment.py": exp_file.read_text() if exp_file.exists() else ""}

        while run_id <= self.config.max_runs:
            if current_iter >= self.config.max_iters_per_run:
                logger.warning(f"Max iterations ({self.config.max_iters_per_run}) reached for run {run_id}")
                break

            # LLM modifies code
            modified_files = self.llm_code_fn(prompt, files)
            if modified_files is None or "ALL_COMPLETED" in str(modified_files):
                logger.info("LLM signaled ALL_COMPLETED")
                break

            # Write modified files back
            for fname, content in modified_files.items():
                if isinstance(content, str):
                    (work_dir / fname).write_text(content, encoding="utf-8")
                    files[fname] = content

            # Execute
            run_info = self._execute_run(work_dir, run_id)
            runs.append(run_info)

            if run_info.success:
                # Build next prompt with results
                prompt = (
                    f"Run {run_id} completed successfully.\n"
                    f"Results: {json.dumps(run_info.metrics, indent=2)}\n"
                    f"Implement the next experiment, or respond 'ALL_COMPLETED' if done."
                )
                run_id += 1
                current_iter = 0
            else:
                # Build retry prompt with error
                prompt = (
                    f"Run {run_id} FAILED.\n"
                    f"Error: {run_info.stderr[-MAX_ITERS*100:]}\n"
                    f"Fix the experiment.py and try again."
                )
                current_iter += 1

        return runs

    def _execute_run(self, work_dir: Path, run_id: int) -> RunInfo:
        """Execute a single experiment run."""
        out_dir = work_dir / f"run_{run_id}"
        out_dir.mkdir(exist_ok=True)

        exec_result = self.sandbox.run_command(
            cmd=["python", "experiment.py", f"--out_dir=run_{run_id}"],
            working_dir=work_dir,
        )

        # Try to load final_info.json
        metrics = {}
        final_info = out_dir / "final_info.json"
        if final_info.exists():
            try:
                with open(final_info) as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    metrics = {k: v.get("means", v) if isinstance(v, dict) else v for k, v in raw.items()}
            except (json.JSONDecodeError, AttributeError):
                pass

        # Fallback: metrics from stdout
        if not metrics and exec_result.metrics:
            metrics = exec_result.metrics

        return RunInfo(
            run_id=run_id,
            success=exec_result.success,
            metrics=metrics,
            stdout=exec_result.stdout,
            stderr=exec_result.stderr,
            elapsed_seconds=exec_result.elapsed_seconds,
            artifacts=exec_result.artifacts,
        )

    def _run_plotting(self, work_dir: Path, result: ExperimentResult) -> None:
        """LLM modifies plot.py and runs it."""
        plot_file = work_dir / "plot.py"
        if not plot_file.exists():
            return

        files = {"plot.py": plot_file.read_text()}
        modified = self.llm_code_fn(PLOT_PROMPT, files)
        if modified and "plot.py" in modified:
            plot_file.write_text(modified["plot.py"], encoding="utf-8")

        for attempt in range(self.config.max_iters_per_run):
            exec_result = self.sandbox.run_command(
                cmd=["python", "plot.py"], working_dir=work_dir
            )
            if exec_result.success:
                # Collect plot files
                result.plots = [str(p) for p in work_dir.glob("*.png")]
                result.plots.extend(str(p) for p in work_dir.glob("*.pdf"))
                return
            # Retry if failed
            if self.llm_code_fn:
                modified = self.llm_code_fn(
                    f"plot.py failed:\n{exec_result.stderr[:500]}\nFix it.",
                    {"plot.py": plot_file.read_text()}
                )
                if modified and "plot.py" in modified:
                    plot_file.write_text(modified["plot.py"], encoding="utf-8")

    def _generate_notes(self, work_dir: Path, result: ExperimentResult) -> None:
        """LLM writes experiment notes."""
        notes_file = work_dir / "notes.txt"
        files = {"notes.txt": notes_file.read_text() if notes_file.exists() else ""}
        modified = self.llm_code_fn(NOTES_PROMPT, files)
        if modified and "notes.txt" in modified:
            notes_file.write_text(modified["notes.txt"], encoding="utf-8")
            result.notes = modified["notes.txt"]

"""AR-style autonomous research loop — central orchestrator.

Inspired by Karpathy's AutoResearch: program.md → edit → evaluate → commit/revert → repeat.
Each scenario profile acts as the 'program.md' equivalent, defining objectives,
constraints, evaluation criteria, and search scope.

The loop orchestrates ALL IdeaClaw modules:
  - source/       → search() + cache + novelty check
  - llm/          → generate() via BYOK or IDE-native
  - evidence/     → verify()
  - quality/      → evaluate()
  - export/       → export()
  - sandbox/      → experiment()
  - reasoning/    → reason()
  - knowledge/    → memory + skills + preferences (Layer 1)
  - library/      → ingester + style + retriever + personalize (Layer 2)
  - orchestrator/ → evolution (idea mutation/crossover)

All modules flow through this orchestrator. The Personalizer assembles
context from all layers before each LLM call.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

import yaml

logger = logging.getLogger(__name__)

__all__ = ["EvalCriterion", "SearchConfig", "StyleConfig", "ExperimentConfig", "ScenarioProfile", "load_profile", "load_all_profiles", "IterationResult", "LoopState", "SearchHook", "GenerateHook", "EvaluateHook", "LearnHook", "ResearchLoop"]


# ---------------------------------------------------------------------------
# Scenario Profile — the 'program.md' equivalent
# ---------------------------------------------------------------------------

@dataclass
class EvalCriterion:
    """A single evaluation criterion with weight and minimum threshold."""
    name: str
    weight: float = 1.0
    min_score: float = 0.0
    description: str = ""


@dataclass
class SearchConfig:
    """Search configuration for a scenario."""
    apis: List[str] = field(default_factory=lambda: ["arxiv", "semantic_scholar"])
    domains: List[str] = field(default_factory=list)
    recency_years: int = 5
    min_sources: int = 5
    max_sources: int = 50
    require_doi: bool = False
    language: str = "en"


@dataclass
class StyleConfig:
    """Style constraints for output."""
    formality: float = 0.8          # 0.0 (casual) - 1.0 (formal)
    voice: str = "third_person"     # first_person | third_person | mixed
    tense: str = "present"         # present | past | mixed
    citation_style: str = "natbib"  # natbib | apa | mla | chicago | ieee
    max_pages: int = 0              # 0 = unlimited
    required_sections: List[str] = field(default_factory=list)
    terminology_registry: str = ""   # e.g. "ml_standard", "medical"


@dataclass
class ExperimentConfig:
    """Experiment/sandbox configuration."""
    enabled: bool = False
    timeout_seconds: int = 300
    metric_name: str = "val_bpb"
    metric_direction: str = "minimize"  # minimize | maximize
    max_iterations: int = 10


@dataclass
class ScenarioProfile:
    """Complete scenario definition — equivalent to AR's program.md.

    Each scenario profile defines:
    - WHAT to produce (objective, format)
    - HOW to search (APIs, domains, recency)
    - HOW to evaluate (criteria, weights, thresholds)
    - STYLE requirements (formality, voice, citation)
    - ITERATION policy (max iterations, target score)
    """
    scenario_id: str
    display_name: str
    category: str                    # academic_ml | academic_bio | business | legal | etc.
    objective: str = ""              # Natural language goal
    
    # Evaluation
    criteria: List[EvalCriterion] = field(default_factory=list)
    target_score: float = 0.85       # Stop iterating when reached
    min_score: float = 0.6           # Below this = revert

    # Search
    search: SearchConfig = field(default_factory=SearchConfig)

    # Style
    style: StyleConfig = field(default_factory=StyleConfig)

    # Experiment
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)

    # Iteration policy (AR-style)
    max_iterations: int = 5
    time_budget_minutes: int = 0     # 0 = unlimited

    # Prompt stage overrides (loaded from prompts/)
    prompt_stages: Dict[str, str] = field(default_factory=dict)

    # Metadata
    version: str = "1.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)


def load_profile(path: Path) -> ScenarioProfile:
    """Load a scenario profile from a YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    
    # Parse nested configs
    search_data = data.pop("search", {})
    style_data = data.pop("style", {})
    experiment_data = data.pop("experiment", {})
    criteria_data = data.pop("criteria", [])
    eval_data = data.pop("evaluation", {})

    search = SearchConfig(**search_data) if search_data else SearchConfig()
    style = StyleConfig(**style_data) if style_data else StyleConfig()
    experiment = ExperimentConfig(**experiment_data) if experiment_data else ExperimentConfig()
    
    criteria = []
    for c in criteria_data:
        criteria.append(EvalCriterion(**c) if isinstance(c, dict) else EvalCriterion(name=str(c)))
    
    # Merge top-level evaluation into profile
    target = eval_data.get("target_score", data.get("target_score", 0.85))
    min_s = eval_data.get("min_score", data.get("min_score", 0.6))
    
    # Extract eval criteria from evaluation block
    if not criteria and "criteria" in eval_data:
        for name, spec in eval_data["criteria"].items():
            if isinstance(spec, dict):
                # Remap YAML shorthand: 'min' → 'min_score'
                if "min" in spec and "min_score" not in spec:
                    spec["min_score"] = spec.pop("min")
                criteria.append(EvalCriterion(name=name, **spec))
            else:
                criteria.append(EvalCriterion(name=name, weight=float(spec)))

    data.pop("target_score", None)
    data.pop("min_score", None)

    return ScenarioProfile(
        search=search, style=style, experiment=experiment,
        criteria=criteria, target_score=target, min_score=min_s,
        **{k: v for k, v in data.items() if k in ScenarioProfile.__dataclass_fields__},
    )


def load_all_profiles(profiles_dir: Path) -> Dict[str, ScenarioProfile]:
    """Load all scenario profiles from a directory."""
    profiles = {}
    for f in sorted(profiles_dir.glob("*.yaml")):
        try:
            profile = load_profile(f)
            profiles[profile.scenario_id] = profile
            logger.debug("Loaded profile: %s", profile.scenario_id)
        except Exception as e:
            logger.warning("Failed to load profile %s: %s", f, e)
    return profiles


# ---------------------------------------------------------------------------
# Iteration State — tracks each loop iteration
# ---------------------------------------------------------------------------

@dataclass
class IterationResult:
    """Result from a single loop iteration."""
    iteration: int
    score: float
    scores_detail: Dict[str, float] = field(default_factory=dict)
    accepted: bool = False
    draft_path: str = ""
    sources_count: int = 0
    elapsed_seconds: float = 0.0
    failure_reason: str = ""
    timestamp: str = ""


@dataclass
class LoopState:
    """Complete state of a research loop run."""
    run_id: str
    profile_id: str
    status: str = "pending"         # pending | running | completed | failed | stopped
    iterations: List[IterationResult] = field(default_factory=list)
    best_score: float = 0.0
    best_iteration: int = -1
    current_draft: Optional[str] = None
    started_at: str = ""
    finished_at: str = ""
    total_elapsed: float = 0.0

    @property
    def iteration_count(self) -> int:
        return len(self.iterations)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "profile_id": self.profile_id,
            "status": self.status,
            "best_score": self.best_score,
            "best_iteration": self.best_iteration,
            "iteration_count": self.iteration_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_elapsed": self.total_elapsed,
            "iterations": [
                {
                    "iteration": r.iteration,
                    "score": r.score,
                    "accepted": r.accepted,
                    "scores_detail": r.scores_detail,
                    "sources_count": r.sources_count,
                    "elapsed_seconds": r.elapsed_seconds,
                    "failure_reason": r.failure_reason,
                }
                for r in self.iterations
            ],
        }


# ---------------------------------------------------------------------------
# Module Hooks — protocols for pluggable modules
# ---------------------------------------------------------------------------

class SearchHook(Protocol):
    """Hook for source search modules."""
    def __call__(self, profile: ScenarioProfile, context: Dict[str, Any]) -> List[Any]: ...


class GenerateHook(Protocol):
    """Hook for draft generation modules."""
    def __call__(self, profile: ScenarioProfile, sources: List[Any],
                 previous_draft: Optional[str], feedback: str) -> str: ...


class EvaluateHook(Protocol):
    """Hook for evaluation modules."""
    def __call__(self, profile: ScenarioProfile, draft: str,
                 sources: List[Any]) -> Dict[str, float]: ...


class LearnHook(Protocol):
    """Hook for learning from failures (memory)."""
    def __call__(self, profile: ScenarioProfile, draft: str,
                 scores: Dict[str, float], failure_reason: str) -> None: ...


# ---------------------------------------------------------------------------
# ResearchLoop — the core AR-style autonomous loop
# ---------------------------------------------------------------------------

class ResearchLoop:
    """AR-style autonomous research loop.

    Usage:
        loop = ResearchLoop(
            search_fn=my_search,
            generate_fn=my_generate,
            evaluate_fn=my_evaluate,
        )
        
        profile = load_profile(Path("profiles/icml_2025.yaml"))
        state = loop.run(profile)
        
        print(f"Best score: {state.best_score} at iteration {state.best_iteration}")
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        idea: str = "",
        search_fn: Optional[SearchHook] = None,
        generate_fn: Optional[GenerateHook] = None,
        evaluate_fn: Optional[EvaluateHook] = None,
        learn_fn: Optional[LearnHook] = None,
        versioning: Optional[Any] = None,
        output_dir: Optional[Path] = None,
        llm_callable: Optional[Callable[[str], str]] = None,
        enable_memory: bool = True,
        enable_library: bool = True,
        enable_novelty: bool = True,
        enable_evolution: bool = False,
        adaptive_depth: bool = True,
        checkpoint_every: int = 1,
        plateau_patience: int = 3,
        plateau_threshold: float = 0.01,
    ):
        self._hooks = None
        self._idea = idea
        self._personalizer = None
        self._novelty_checker = None
        self._evolver = None
        self.adaptive_depth = adaptive_depth
        self.checkpoint_every = checkpoint_every
        self.plateau_patience = plateau_patience
        self.plateau_threshold = plateau_threshold

        # Auto-wire LLMHooks (BYOK or IDE-native)
        if config is not None and not generate_fn:
            from ideaclaw.orchestrator.hooks import LLMHooks
            hooks = LLMHooks(config, idea=idea, output_dir=output_dir,
                             llm_callable=llm_callable)
            search_fn = search_fn or hooks.search
            generate_fn = hooks.generate
            evaluate_fn = evaluate_fn or hooks.evaluate
            learn_fn = learn_fn or hooks.learn
            self._hooks = hooks
            mode = "IDE-native" if llm_callable else "BYOK"
            logger.info("Auto-wired LLMHooks (%s)", mode)
        elif llm_callable and not generate_fn:
            from ideaclaw.orchestrator.hooks import LLMHooks
            hooks = LLMHooks(None, idea=idea, output_dir=output_dir,
                             llm_callable=llm_callable)
            search_fn = search_fn or hooks.search
            generate_fn = hooks.generate
            evaluate_fn = evaluate_fn or hooks.evaluate
            learn_fn = learn_fn or hooks.learn
            self._hooks = hooks
            logger.info("Auto-wired LLMHooks (IDE-native)")

        self.search_fn = search_fn
        self.generate_fn = generate_fn
        self.evaluate_fn = evaluate_fn
        self.learn_fn = learn_fn
        self.versioning = versioning
        self.output_dir = output_dir or Path.home() / ".ideaclaw" / "runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # --- Layer 1 + Layer 2: Personalizer (memory, skills, prefs, library, style) ---
        if enable_memory or enable_library:
            try:
                from ideaclaw.library.personalize import Personalizer
                self._personalizer = Personalizer()
                logger.info("Personalizer enabled (memory + library)")
            except Exception as e:
                logger.debug("Personalizer not available: %s", e)

        # --- Novelty detection ---
        if enable_novelty:
            try:
                from ideaclaw.source.novelty import NoveltyChecker
                self._novelty_checker = NoveltyChecker()
                logger.info("Novelty checker enabled")
            except Exception as e:
                logger.debug("NoveltyChecker not available: %s", e)

        # --- Idea evolution ---
        if enable_evolution:
            try:
                from ideaclaw.orchestrator.evolution import IdeaEvolver
                self._evolver = IdeaEvolver(llm_callable=llm_callable)
                logger.info("Idea evolver enabled")
            except Exception as e:
                logger.debug("IdeaEvolver not available: %s", e)

    @classmethod
    def from_ide(cls, llm_callable: Callable[[str], str], idea: str = "", **kwargs):
        """Factory for IDE-native mode — IDE provides the LLM callable.

        Usage:
            loop = ResearchLoop.from_ide(my_llm_fn, idea="attention mechanisms")
            state = loop.run(profile)
        """
        return cls(llm_callable=llm_callable, idea=idea, **kwargs)

    def run(
        self,
        profile: ScenarioProfile,
        run_id: Optional[str] = None,
        resume_state: Optional[LoopState] = None,
    ) -> LoopState:
        """Execute the AR-style autonomous loop for a scenario.

        The loop:
          1. Search sources (using profile's search config)
          2. Generate draft (using profile's prompt stages)
          3. Evaluate (using profile's criteria)
          4. If score >= min_score → commit (accept)
             If score >= target_score → stop (done!)
             If score < min_score → revert + learn from failure
          5. Repeat until target_score reached or max_iterations exhausted

        Args:
            profile: The scenario profile (equivalent to AR's program.md)
            run_id: Optional run ID. Auto-generated if not provided.
            resume_state: Optional previous state to resume from.

        Returns:
            LoopState with full run history.
        """
        if run_id is None:
            run_id = f"{profile.scenario_id}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"

        state = resume_state or LoopState(
            run_id=run_id,
            profile_id=profile.scenario_id,
            started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        state.status = "running"

        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Time budget enforcement (AR: 5 min per experiment)
        time_limit = profile.time_budget_minutes * 60 if profile.time_budget_minutes > 0 else float("inf")
        loop_start = time.monotonic()

        logger.info("Starting loop: %s (profile=%s, max_iter=%d, target=%.2f)",
                     run_id, profile.scenario_id, profile.max_iterations, profile.target_score)

        # --- PRE-RUN: Personalize + Novelty + Evolution ---
        personal_context = ""
        novelty_info = ""
        idea_text = self._idea or profile.objective

        # Step 0a: Build personalized context (memory + skills + preferences + library)
        if self._personalizer:
            try:
                ctx = self._personalizer.build_context(
                    idea=idea_text,
                    category=profile.category,
                    scenario_id=profile.scenario_id,
                )
                if not ctx.is_empty():
                    personal_context = ctx.full_prompt
                    logger.info("Personalized context: %d chars", len(personal_context))
            except Exception as e:
                logger.debug("Personalization failed: %s", e)

        # Step 0b: Novelty check against existing literature
        if self._novelty_checker and self.search_fn:
            try:
                pre_sources = self.search_fn(profile, {"iteration": -1, "feedback": ""})
                report = self._novelty_checker.check(idea_text, pre_sources[:20])
                is_novel = report.composite_novelty >= 0.5
                if not is_novel:
                    from ideaclaw.source.novelty import novelty_report as fmt_novelty
                    novelty_info = fmt_novelty(report)
                    logger.info("Novelty: %.2f / %s (%d similar)",
                                report.composite_novelty, report.verdict,
                                len(report.most_similar_papers))
                    (run_dir / "novelty_report.json").write_text(
                        json.dumps({"score": report.composite_novelty,
                                    "verdict": report.verdict,
                                    "similar": report.most_similar_papers[:5],
                                    "explanation": report.explanation}, indent=2),
                        encoding="utf-8")
            except Exception as e:
                logger.debug("Novelty check failed: %s", e)

        # Step 0c: Evolve idea variants (optional)
        if self._evolver and idea_text:
            try:
                variants = self._evolver.mutate(idea_text, n_variants=2,
                                                 feedback=novelty_info)
                if variants:
                    logger.info("Evolution: %d variants generated", len(variants))
                    (run_dir / "idea_variants.json").write_text(
                        json.dumps(variants, indent=2, ensure_ascii=False),
                        encoding="utf-8")
            except Exception as e:
                logger.debug("Evolution failed: %s", e)

        # Inject pre-loop context into initial feedback
        feedback = ""
        if personal_context or novelty_info:
            feedback = "\n".join(filter(None, [personal_context, novelty_info]))

        start_iter = state.iteration_count

        for i in range(start_iter, profile.max_iterations):
            iter_start = time.monotonic()

            # Check time budget
            elapsed_total = time.monotonic() - loop_start
            if elapsed_total >= time_limit:
                logger.info("Time budget exhausted (%.0fs)", elapsed_total)
                state.status = "stopped"
                break

            logger.info("Iteration %d/%d", i + 1, profile.max_iterations)

            try:
                # Step 1: SEARCH
                sources = []
                if self.search_fn:
                    sources = self.search_fn(profile, {"iteration": i, "feedback": feedback})
                    logger.info("  Search: %d sources found", len(sources))

                # Step 2: GENERATE
                draft = ""
                if self.generate_fn:
                    draft = self.generate_fn(profile, sources, state.current_draft, feedback)
                    logger.info("  Generate: %d chars", len(draft))

                # Save draft to disk
                draft_path = run_dir / f"draft_iter{i:03d}.md"
                draft_path.write_text(draft, encoding="utf-8")

                # Step 3: EVALUATE
                scores = {}
                composite = 0.0
                if self.evaluate_fn:
                    scores = self.evaluate_fn(profile, draft, sources)
                    composite = self._compute_composite(profile, scores)
                    logger.info("  Evaluate: composite=%.3f (%s)", composite,
                                ", ".join(f"{k}={v:.2f}" for k, v in sorted(scores.items())))

                iter_elapsed = time.monotonic() - iter_start

                # Step 4: AR DECISION — accept or revert
                result = IterationResult(
                    iteration=i,
                    score=composite,
                    scores_detail=scores,
                    draft_path=str(draft_path),
                    sources_count=len(sources),
                    elapsed_seconds=round(iter_elapsed, 2),
                    timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
                )

                if composite >= profile.min_score:
                    # ACCEPT — score is above minimum
                    result.accepted = True
                    state.current_draft = draft

                    if self.versioning:
                        self.versioning.commit(run_id, i, draft, composite, scores)

                    if composite > state.best_score:
                        state.best_score = composite
                        state.best_iteration = i

                    logger.info("  ACCEPT (%.3f >= %.3f min)", composite, profile.min_score)

                    if composite >= profile.target_score:
                        state.iterations.append(result)
                        logger.info("  TARGET REACHED (%.3f >= %.3f)", composite, profile.target_score)
                        state.status = "completed"
                        break
                    else:
                        # Accepted but not yet at target — continue improving
                        feedback = self._generate_feedback(profile, scores)

                        # Adaptive depth: stop early if plateaued
                        if self.adaptive_depth and self._is_plateaued(state):
                            logger.info("  PLATEAU detected (%d iters with <%.1f%% improvement), stopping early",
                                        self.plateau_patience, self.plateau_threshold * 100)
                            state.status = "completed"
                            state.iterations.append(result)
                            break

                else:
                    # REVERT — score below minimum
                    result.accepted = False
                    result.failure_reason = self._diagnose_failure(profile, scores)
                    feedback = result.failure_reason

                    if self.versioning:
                        self.versioning.revert(run_id, i)

                    if self.learn_fn:
                        self.learn_fn(profile, draft, scores, result.failure_reason)

                    logger.info("  REVERT (%.3f < %.3f min): %s",
                                composite, profile.min_score, result.failure_reason[:100])

                state.iterations.append(result)

                # Checkpoint after every N iterations
                if self.checkpoint_every > 0 and (i + 1) % self.checkpoint_every == 0:
                    self._save_checkpoint(state, run_dir)

            except Exception as e:
                logger.error("  Iteration %d failed: %s", i, e)
                state.iterations.append(IterationResult(
                    iteration=i, score=0, failure_reason=str(e),
                    elapsed_seconds=round(time.monotonic() - iter_start, 2),
                    timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
                ))
                self._save_checkpoint(state, run_dir)

        # Finalize
        if state.status == "running":
            state.status = "completed" if state.best_score >= profile.target_score else "failed"

        state.finished_at = dt.datetime.now(dt.timezone.utc).isoformat()
        state.total_elapsed = round(time.monotonic() - loop_start, 2)

        # Save state to disk
        state_path = run_dir / "state.json"
        state_path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        # Finalize outputs (document, train.md, usage, summary)
        if self._hooks and hasattr(self._hooks, "finalize_output"):
            try:
                outputs = self._hooks.finalize_output(profile, state, run_dir)
                logger.info("Outputs saved: %s", ", ".join(f"{k}={v}" for k, v in outputs.items()))
            except Exception as e:
                logger.warning("Output finalization failed: %s", e)
        elif self.versioning and state.current_draft:
            (run_dir / "output.md").write_text(state.current_draft, encoding="utf-8")

        # --- POST-RUN: Learn from experience (update memory + extract skills) ---
        if self._personalizer:
            try:
                score_history = [r.score for r in state.iterations]
                feedback_list = [r.failure_reason for r in state.iterations if r.failure_reason]
                self._personalizer.learn_from_run(
                    run_id=run_id,
                    idea=idea_text,
                    category=profile.category,
                    scenario_id=profile.scenario_id,
                    final_score=state.best_score,
                    iteration_count=state.iteration_count,
                    score_history=score_history,
                    feedback_history=feedback_list,
                )
                logger.info("Post-run learning: memory + skills updated")
            except Exception as e:
                logger.debug("Post-run learning failed: %s", e)

        logger.info("Loop finished: status=%s, best=%.3f (iter %d), %d iterations, %.1fs",
                     state.status, state.best_score, state.best_iteration,
                     state.iteration_count, state.total_elapsed)

        return state

    def _compute_composite(self, profile: ScenarioProfile, scores: Dict[str, float]) -> float:
        """Compute weighted composite score from criteria."""
        if not profile.criteria:
            # No criteria defined — simple average
            return sum(scores.values()) / max(1, len(scores)) if scores else 0.0

        total_weight = sum(c.weight for c in profile.criteria)
        if total_weight == 0:
            return 0.0

        weighted_sum = 0.0
        for criterion in profile.criteria:
            score = scores.get(criterion.name, 0.0)
            # Penalty if below minimum threshold
            if criterion.min_score > 0 and score < criterion.min_score:
                score *= 0.5  # Harsh penalty for failing minimum
            weighted_sum += criterion.weight * score

        return weighted_sum / total_weight

    def _generate_feedback(self, profile: ScenarioProfile, scores: Dict[str, float]) -> str:
        """Generate actionable feedback for next iteration based on scores."""
        weak = []
        for criterion in profile.criteria:
            score = scores.get(criterion.name, 0.0)
            if score < criterion.min_score:
                weak.append(f"{criterion.name}: {score:.2f} (need ≥{criterion.min_score:.2f})")
            elif score < 0.8:
                weak.append(f"{criterion.name}: {score:.2f} (room to improve)")

        if not weak:
            # All criteria met — find lowest
            if scores:
                lowest = min(scores, key=scores.get)
                weak.append(f"Improve {lowest} ({scores[lowest]:.2f})")

        return "Focus on: " + "; ".join(weak) if weak else "All criteria met."

    def _diagnose_failure(self, profile: ScenarioProfile, scores: Dict[str, float]) -> str:
        """Diagnose why a draft was rejected."""
        failures = []
        for criterion in profile.criteria:
            score = scores.get(criterion.name, 0.0)
            if score < criterion.min_score:
                gap = criterion.min_score - score
                failures.append(f"{criterion.name} missed by {gap:.2f} ({score:.2f}<{criterion.min_score:.2f})")

        if not failures:
            composite = self._compute_composite(profile, scores)
            failures.append(f"Composite {composite:.2f} < {profile.min_score:.2f} minimum")

        return "; ".join(failures)

    def _is_plateaued(self, state: LoopState) -> bool:
        """Detect if score improvement has plateaued.

        Returns True if the last `plateau_patience` accepted iterations
        showed less than `plateau_threshold` improvement.
        """
        accepted = [r for r in state.iterations if r.accepted]
        if len(accepted) < self.plateau_patience + 1:
            return False
        recent = accepted[-self.plateau_patience:]
        baseline = accepted[-(self.plateau_patience + 1)].score
        max_recent = max(r.score for r in recent)
        improvement = max_recent - baseline
        return improvement < self.plateau_threshold

    @staticmethod
    def _save_checkpoint(state: LoopState, run_dir: Path) -> None:
        """Save checkpoint to disk for crash recovery."""
        try:
            ckpt_path = run_dir / "checkpoint.json"
            ckpt_path.write_text(
                json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug("Checkpoint saved → %s", ckpt_path)
        except Exception as e:
            logger.warning("Checkpoint save failed: %s", e)

    @staticmethod
    def load_checkpoint(run_dir: Path) -> Optional[LoopState]:
        """Load a checkpoint from disk for warm restart.

        Args:
            run_dir: Path to the run directory.

        Returns:
            LoopState if checkpoint exists, None otherwise.
        """
        ckpt_path = run_dir / "checkpoint.json"
        if not ckpt_path.exists():
            return None
        try:
            data = json.loads(ckpt_path.read_text(encoding="utf-8"))
            state = LoopState(
                run_id=data["run_id"],
                profile_id=data["profile_id"],
                status=data.get("status", "running"),
                best_score=data.get("best_score", 0.0),
                best_iteration=data.get("best_iteration", -1),
                started_at=data.get("started_at", ""),
            )
            for it_data in data.get("iterations", []):
                state.iterations.append(IterationResult(
                    iteration=it_data.get("iteration", 0),
                    score=it_data.get("score", 0.0),
                    scores_detail=it_data.get("scores_detail", {}),
                    accepted=it_data.get("accepted", False),
                    failure_reason=it_data.get("failure_reason", ""),
                ))
            logger.info("Loaded checkpoint: %d iterations, best=%.3f",
                        len(state.iterations), state.best_score)
            return state
        except Exception as e:
            logger.warning("Checkpoint load failed: %s", e)
            return None

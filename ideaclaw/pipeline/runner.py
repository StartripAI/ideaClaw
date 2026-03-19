"""Main pipeline runner — orchestrates all 15 stages with real LLM calls.

Integrates ported AI-Scientist modules:
- Stage 4 (SOURCE_COLLECT): Semantic Scholar academic search
- Stage 14 (TRUST_REVIEW): NeurIPS-style structured peer review
- Stage 15 (EXPORT_PUBLISH): Citation enrichment + optional LaTeX
"""

from __future__ import annotations
import logging

import datetime as dt
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table

from ideaclaw.llm.client import LLMClient
from ideaclaw.pipeline.stages import Stage, STAGE_ORDER
from ideaclaw.pipeline.state import PipelineState, StageResult
from ideaclaw.prompts import PromptEngine
from ideaclaw.utils.io import write_json

logger = logging.getLogger(__name__)

# --- ARC Module Imports (ported from AI-Scientist) ---
try:
    from ideaclaw.source.scholar import search_for_papers, PaperResult
    HAS_SCHOLAR = True
except ImportError:
    HAS_SCHOLAR = False

try:
    from ideaclaw.review.reviewer import PeerReviewer, ReviewResult
    from ideaclaw.review.structured import REVIEW_FIELDS
    HAS_REVIEWER = True
except ImportError:
    HAS_REVIEWER = False

try:
    from ideaclaw.source.citation import CitationManager
    HAS_CITATION = True
except ImportError:
    HAS_CITATION = False

try:
    from ideaclaw.export.latex_compiler import LatexCompiler, validate_latex
    HAS_LATEX = True
except ImportError:
    HAS_LATEX = False

# --- Template System (deliverable templates) ---
try:
    from ideaclaw.templates.template_loader import TemplateLoader
    HAS_TEMPLATES = True
except ImportError:
    HAS_TEMPLATES = False

# --- ARC Full Module Imports (complete port) ---
try:
    from ideaclaw.arc.generate_ideas import generate_ideas as arc_generate_ideas
    from ideaclaw.arc.generate_ideas import check_idea_novelty as arc_check_novelty
    from ideaclaw.arc.generate_ideas import search_for_papers as arc_search_papers
    HAS_ARC_IDEAS = True
except ImportError:
    HAS_ARC_IDEAS = False

try:
    from ideaclaw.arc.perform_experiments import (
        perform_experiments as arc_perform_experiments,
        run_experiment as arc_run_experiment,
        run_plotting as arc_run_plotting,
        coder_prompt as ARC_CODER_PROMPT,
        MAX_RUNS as ARC_MAX_RUNS,
        MAX_ITERS as ARC_MAX_ITERS,
    )
    HAS_ARC_EXPERIMENTS = True
except ImportError:
    HAS_ARC_EXPERIMENTS = False

try:
    from ideaclaw.arc.perform_writeup import (
        perform_writeup as arc_perform_writeup,
        per_section_tips as ARC_SECTION_TIPS,
        compile_latex as arc_compile_latex,
        get_citation_aider_prompt as arc_get_citation_prompt,
        refinement_prompt as ARC_REFINEMENT_PROMPT,
        second_refinement_prompt as ARC_SECOND_REFINEMENT_PROMPT,
    )
    HAS_ARC_WRITEUP = True
except ImportError:
    HAS_ARC_WRITEUP = False

try:
    from ideaclaw.arc.perform_review import (
        perform_review as arc_perform_review,
        neurips_form as ARC_NEURIPS_FORM,
        get_meta_review as arc_get_meta_review,
        perform_improvement as arc_perform_improvement,
    )
    HAS_ARC_REVIEW = True
except ImportError:
    HAS_ARC_REVIEW = False

try:
    from ideaclaw.arc.llm import (
        create_client as arc_create_client,
        get_response_from_llm as arc_get_response,
        extract_json_between_markers as arc_extract_json,
        AVAILABLE_LLMS as ARC_AVAILABLE_LLMS,
    )
    HAS_ARC_LLM = True
except ImportError:
    HAS_ARC_LLM = False

try:
    from ideaclaw.sandbox.executor import SandboxExecutor, SandboxConfig
    from ideaclaw.sandbox.experiment_runner import ExperimentRunner
    HAS_SANDBOX = True
except ImportError:
    HAS_SANDBOX = False

__all__ = ['RunResult', 'PipelineRunner']

console = Console()


@dataclass
class RunResult:
    """Final result of a pipeline run."""
    run_id: str
    success: bool
    output_dir: Path
    failed_stage: Optional[str] = None
    error: Optional[str] = None


def _make_run_id() -> str:
    """Generate a unique run ID: ic-YYYYMMDD-HHMMSS-<hash>."""
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.strftime("%Y%m%d-%H%M%S")
    h = hashlib.sha256(f"{ts}-{id(now)}".encode()).hexdigest()[:8]
    return f"ic-{ts}-{h}"


# Map stage prompt_key → which subdirectory to write artifacts to
_ARTIFACT_DIR_MAP = {
    "idea_init": "reasoning",
    "idea_decompose": "reasoning",
    "search_strategy": "evidence",
    "source_collect": "evidence",
    "source_screen": "evidence",
    "evidence_extract": "evidence",
    "evidence_gate": "evidence",
    "claim_verify": "evidence",
    "evidence_synthesis": "reasoning",
    "decision_tree": "reasoning",
    "counterargument_gen": "reasoning",
    "pack_outline": ".",
    "pack_draft": ".",
    "trust_review": "trust",
    "export_publish": ".",
}


class PipelineRunner:
    """Orchestrates the 15-stage IdeaClaw pipeline with real LLM calls."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.prompts = PromptEngine(config.get("prompts", {}).get("custom_file"))
        self.auto_approve = config.get("security", {}).get("auto_approve", False)
        self.llm = LLMClient(config.get("llm", {}))
        self.repo_root = Path.cwd()

    def run(self) -> RunResult:
        """Execute a full pipeline run."""
        run_id = _make_run_id()
        run_dir = self.repo_root / "artifacts" / run_id
        self._ensure_run_layout(run_dir)

        state = PipelineState(run_id=run_id, run_dir=run_dir)
        state.context["idea_text"] = self.config["idea"]["text"]
        state.context["pack_type"] = self.config["idea"]["pack_type"]
        state.context["language"] = self.config["idea"]["language"]

        # Write manifest
        manifest = {
            "run_id": run_id,
            "idea": self.config["idea"]["text"],
            "pack_type": self.config["idea"]["pack_type"],
            "language": self.config["idea"]["language"],
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "config": {k: v for k, v in self.config.items() if k != "llm"},  # redact keys
        }
        write_json(run_dir / "manifest.json", manifest)

        return self._execute(state)

    def resume(self, run_id: str) -> RunResult:
        """Resume a pipeline from checkpoint."""
        run_dir = self.repo_root / "artifacts" / run_id
        state = PipelineState.load_checkpoint(run_dir)
        if state is None:
            return RunResult(
                run_id=run_id,
                success=False,
                output_dir=run_dir,
                error=f"No checkpoint found in {run_dir}",
            )
        state.status = "running"
        return self._execute(state)

    def _execute(self, state: PipelineState) -> RunResult:
        """Core execution loop."""
        state.status = "running"
        self._print_header(state)

        while not state.is_complete:
            stage = state.current_stage
            info = stage.info

            console.print(
                f"\n[bold]Stage {info.number}/15:[/bold] {info.name} "
                f"[dim]({info.phase.name})[/dim]"
            )

            # Gate check
            if info.is_gate and not self.auto_approve:
                if not self._request_approval(stage):
                    state.record_result(StageResult(stage=stage, status="gate_rejected"))
                    if info.rollback_target:
                        console.print(
                            f"  [yellow]↩ Rolling back to stage {info.rollback_target}[/yellow]"
                        )
                        state.rollback_to(info.rollback_target)
                        state.save_checkpoint()
                        continue
                    else:
                        state.status = "failed"
                        state.save_checkpoint()
                        return RunResult(
                            run_id=state.run_id,
                            success=False,
                            output_dir=state.run_dir,
                            failed_stage=info.name,
                            error="Gate rejected by user",
                        )

            # Execute stage
            start = time.monotonic()
            try:
                result = self._execute_stage(stage, state)
            except Exception as exc:
                result = StageResult(
                    stage=stage,
                    status="failed",
                    error=f"{exc.__class__.__name__}: {exc}",
                )

            result.duration_sec = time.monotonic() - start
            state.record_result(result)

            if result.status == "failed":
                console.print(f"  [red]✗ Failed: {result.error}[/red]")
                state.status = "failed"
                state.save_checkpoint()
                return RunResult(
                    run_id=state.run_id,
                    success=False,
                    output_dir=state.run_dir,
                    failed_stage=info.name,
                    error=result.error,
                )

            console.print(
                f"  [green]✓ Completed[/green] [dim]({result.duration_sec:.1f}s)[/dim]"
            )

            # Store stage output in context for downstream stages
            state.context[info.prompt_key] = result.output.get("response", "")
            state.advance()
            state.save_checkpoint()

        # Pipeline complete — write final pack.md
        state.status = "completed"
        self._write_final_pack(state)
        state.save_checkpoint()
        self._print_summary(state)

        return RunResult(
            run_id=state.run_id,
            success=True,
            output_dir=state.run_dir,
        )

    def _execute_stage(self, stage: Stage, state: PipelineState) -> StageResult:
        """Execute a single pipeline stage.

        Uses ARC modules for specific stages when available,
        falls back to LLM for all others.

        ARC Integration Map:
          Stage 1  (idea_init)         → ARC generate_ideas + novelty check
          Stage 4  (source_collect)    → ARC Semantic Scholar search
          Stage 5  (source_screen)     → ARC experiment execution loop
          Stage 13 (pack_draft)        → ARC LaTeX writeup (per-section + citations)
          Stage 14 (trust_review)      → ARC NeurIPS peer review + ensemble
          Stage 15 (export_publish)    → ARC citation enrichment + LaTeX compilation
        """
        info = stage.info
        arc_mode = self.config.get("arc", {}).get("enabled", True)

        # --- ARC Module Overrides ---
        if arc_mode:
            if info.prompt_key == "idea_init" and HAS_ARC_IDEAS:
                return self._arc_idea_generation(stage, state)
            if info.prompt_key == "source_collect" and HAS_SCHOLAR:
                return self._arc_source_collect(stage, state)
            if info.prompt_key == "source_screen" and HAS_ARC_EXPERIMENTS and HAS_SANDBOX:
                return self._arc_experiment_loop(stage, state)
            if info.prompt_key == "pack_draft" and HAS_ARC_WRITEUP:
                return self._arc_writeup(stage, state)
            if info.prompt_key == "trust_review" and HAS_REVIEWER:
                return self._arc_peer_review(stage, state)
            if info.prompt_key == "export_publish" and HAS_CITATION:
                return self._arc_export(stage, state)

        # --- Default: LLM call ---
        return self._execute_stage_llm(stage, state)

    def _execute_stage_llm(self, stage: Stage, state: PipelineState) -> StageResult:
        """Default stage execution via LLM."""
        info = stage.info
        prompt_vars = dict(state.context)

        system_prompt = self.prompts.get_system_prompt(info.prompt_key)
        user_prompt = self.prompts.get_user_prompt(info.prompt_key, **prompt_vars)
        json_mode = self.prompts.is_json_mode(info.prompt_key)
        max_tokens = self.prompts.get_max_tokens(info.prompt_key)

        response = self.llm.chat_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )

        self._write_stage_artifact(info, state, response, json_mode)

        return StageResult(
            stage=stage,
            status="completed",
            output={"response": response},
        )

    # ------------------------------------------------------------------
    # ARC Module: Semantic Scholar Search (Stage 4)
    # ------------------------------------------------------------------
    def _arc_source_collect(self, stage: Stage, state: PipelineState) -> StageResult:
        """Use Semantic Scholar API for source collection instead of pure LLM."""
        idea_text = state.context.get("idea_text", "")
        search_strategy = state.context.get("search_strategy", idea_text)

        # Extract search queries from strategy or idea
        queries = self._extract_search_queries(search_strategy, idea_text)
        console.print(f"  [cyan]📚 Searching {len(queries)} queries on Semantic Scholar...[/cyan]")

        all_papers = []
        for q in queries:
            try:
                papers = search_for_papers(q, limit=5)
                all_papers.extend(papers)
                console.print(f"  [dim]  '{q[:50]}...' → {len(papers)} papers[/dim]")
            except Exception as e:
                logger.warning(f"Scholar search failed for '{q}': {e}")

        # Deduplicate by title
        seen_titles = set()
        unique_papers = []
        for p in all_papers:
            if p.title.lower() not in seen_titles:
                seen_titles.add(p.title.lower())
                unique_papers.append(p)

        # Format into response text
        lines = [f"## Academic Sources ({len(unique_papers)} papers)\n"]
        for i, p in enumerate(unique_papers[:20], 1):
            lines.append(
                f"{i}. **{p.title}**\n"
                f"   Authors: {p.authors}\n"
                f"   Venue: {p.venue}, {p.year} | Citations: {p.citation_count}\n"
                f"   URL: {p.url}\n"
                f"   Abstract: {p.abstract[:200]}...\n"
            )

        response = "\n".join(lines)

        # Also store structured data
        state.context["_scholar_papers"] = [
            p.to_dict() if hasattr(p, 'to_dict') else {"title": p.title, "url": p.url}
            for p in unique_papers[:20]
        ]

        # Write artifact
        artifact_base = state.run_dir / "evidence"
        artifact_base.mkdir(parents=True, exist_ok=True)
        (artifact_base / "source_collect.md").write_text(response, encoding="utf-8")
        write_json(artifact_base / "scholar_papers.json", state.context["_scholar_papers"])

        console.print(f"  [green]Found {len(unique_papers)} unique papers[/green]")

        return StageResult(
            stage=stage,
            status="completed",
            output={"response": response},
        )

    # ------------------------------------------------------------------
    # ARC Module: NeurIPS Peer Review (Stage 14)
    # ------------------------------------------------------------------
    def _arc_peer_review(self, stage: Stage, state: PipelineState) -> StageResult:
        """Use NeurIPS-style structured peer review instead of simple trust check."""
        draft = state.context.get("pack_draft", state.context.get("export_publish", ""))

        # Create LLM callback for the reviewer
        def llm_call(system: str, user: str) -> str:
            return self.llm.chat_with_fallback(
                system_prompt=system,
                user_prompt=user,
                max_tokens=4096,
            )

        console.print("  [cyan]📝 Running NeurIPS-style peer review...[/cyan]")

        reviewer = PeerReviewer(
            llm_call_fn=llm_call,
            num_reflections=self.config.get("review", {}).get("num_reflections", 3),
            num_ensemble=self.config.get("review", {}).get("num_ensemble", 1),
        )

        try:
            review = reviewer.review(draft)
        except Exception as e:
            logger.warning(f"Peer review failed, falling back to LLM: {e}")
            return self._execute_stage_llm(stage, state)

        # Format review into response
        review_dict = review.to_dict()
        response = (
            f"## NeurIPS-Style Peer Review\n\n"
            f"**Decision: {review.decision}** | Overall: {review.overall}/10 | "
            f"Confidence: {review.confidence}/5\n\n"
            f"### Scores\n"
            f"- Originality: {review.originality}/4\n"
            f"- Quality: {review.quality}/4\n"
            f"- Clarity: {review.clarity}/4\n"
            f"- Significance: {review.significance}/4\n"
            f"- Soundness: {review.soundness}/4\n"
            f"- Presentation: {review.presentation}/4\n"
            f"- Contribution: {review.contribution}/4\n\n"
            f"### Summary\n{review.summary}\n\n"
            f"### Strengths\n" + "\n".join(f"- {s}" for s in review.strengths) + "\n\n"
            f"### Weaknesses\n" + "\n".join(f"- {w}" for w in review.weaknesses) + "\n\n"
            f"### Questions\n" + "\n".join(f"- {q}" for q in review.questions) + "\n"
        )

        # Store review in context
        state.context["_peer_review"] = review_dict

        # Write artifact
        artifact_base = state.run_dir / "trust"
        artifact_base.mkdir(parents=True, exist_ok=True)
        (artifact_base / "trust_review.md").write_text(response, encoding="utf-8")
        write_json(artifact_base / "peer_review.json", review_dict)

        console.print(
            f"  [{'green' if review.is_accept else 'red'}]"
            f"  {review.score_summary}"
            f"[/{'green' if review.is_accept else 'red'}]"
        )

        return StageResult(
            stage=stage,
            status="completed",
            output={"response": response},
        )

    # ------------------------------------------------------------------
    # ARC Module: Citation Enrichment + Export (Stage 15)
    # ------------------------------------------------------------------
    def _arc_export(self, stage: Stage, state: PipelineState) -> StageResult:
        """Enhanced export with citation enrichment."""
        draft = state.context.get("pack_draft", "")

        # Step 1: Citation enrichment (if enabled)
        max_cite_rounds = self.config.get("citation", {}).get("max_rounds", 10)
        if max_cite_rounds > 0:
            console.print(f"  [cyan]📎 Citation enrichment (up to {max_cite_rounds} rounds)...[/cyan]")

            def llm_call(system: str, user: str) -> str:
                return self.llm.chat_with_fallback(
                    system_prompt=system,
                    user_prompt=user,
                    max_tokens=2048,
                )

            try:
                cm = CitationManager(max_rounds=max_cite_rounds)
                enriched, rounds = cm.run_citation_loop(draft, llm_call_fn=llm_call)
                if rounds:
                    console.print(f"  [green]Added citations in {len(rounds)} rounds[/green]")
                    state.context["pack_draft"] = enriched
                    draft = enriched
            except Exception as e:
                logger.warning(f"Citation enrichment failed: {e}")

        # Step 2: Standard LLM export
        result = self._execute_stage_llm(stage, state)

        # Step 3: LaTeX compilation (if enabled and available)
        if HAS_LATEX and self.config.get("export", {}).get("latex", False):
            console.print("  [cyan]📄 Compiling LaTeX...[/cyan]")
            try:
                compiler = LatexCompiler(state.run_dir)
                validation = compiler.validate()
                if validation.is_valid:
                    success = compiler.compile(
                        output_pdf=state.run_dir / "paper.pdf"
                    )
                    if success:
                        console.print("  [green]PDF generated[/green]")
                else:
                    console.print(f"  [yellow]LaTeX validation: {validation.summary()}[/yellow]")
            except Exception as e:
                logger.warning(f"LaTeX compilation failed: {e}")

        return result

    # ------------------------------------------------------------------
    # ARC Module: Idea Generation + Novelty Check (Stage 1)
    # ------------------------------------------------------------------
    def _arc_idea_generation(self, stage: Stage, state: PipelineState) -> StageResult:
        """Use ARC's idea generation with novelty checking via Semantic Scholar."""
        idea_text = state.context.get("idea_text", "")
        template_dir = self.config.get("arc", {}).get("template_dir", "")

        console.print("  [cyan]💡 ARC idea generation + novelty check...[/cyan]")

        # If we have a template directory, use ARC's full idea generation
        if template_dir and HAS_ARC_LLM and Path(template_dir).exists():
            try:
                api_key_env = self.config.get("llm", {}).get("api_key_env", "OPENAI_API_KEY")
                model = self.config.get("arc", {}).get("model", "gpt-4o")
                client, client_model = arc_create_client(model)
                ideas = arc_generate_ideas(
                    base_dir=template_dir,
                    client=client,
                    model=client_model,
                    max_num_generations=self.config.get("arc", {}).get("max_ideas", 3),
                    num_reflections=self.config.get("arc", {}).get("num_reflections", 3),
                )
                # Novelty check
                if self.config.get("arc", {}).get("check_novelty", True):
                    ideas = arc_check_novelty(
                        ideas, base_dir=template_dir,
                        client=client, model=client_model,
                    )
                # Store ideas
                state.context["_arc_ideas"] = ideas
                novel = [i for i in ideas if i.get("novel", True)]
                response = f"## Generated Ideas ({len(ideas)} total, {len(novel)} novel)\n\n"
                for i, idea in enumerate(ideas):
                    response += (
                        f"### {i+1}. {idea.get('Title', idea.get('Name', 'Untitled'))}\n"
                        f"- Novelty: {idea.get('Novelty', '?')}/10 | "
                        f"Feasibility: {idea.get('Feasibility', '?')}/10 | "
                        f"Interestingness: {idea.get('Interestingness', '?')}/10\n"
                        f"- Novel: {'✅' if idea.get('novel', True) else '❌'}\n"
                        f"- Experiment: {idea.get('Experiment', '')}\n\n"
                    )
                console.print(f"  [green]Generated {len(ideas)} ideas, {len(novel)} novel[/green]")
            except Exception as e:
                logger.warning(f"ARC idea generation failed, falling back to LLM: {e}")
                return self._execute_stage_llm(stage, state)
        else:
            # No template — use novelty check on user's idea as a search
            response = f"## Idea Analysis\n\n**Input:** {idea_text}\n\n"
            if HAS_SCHOLAR:
                try:
                    papers = search_for_papers(idea_text, limit=5)
                    if papers:
                        response += f"### Related Papers ({len(papers)} found)\n\n"
                        for p in papers:
                            response += f"- {p.title} ({p.year}, {p.citation_count} cites)\n"
                        state.context["_novelty_papers"] = len(papers)
                except Exception:
                    pass
            # Fall through to LLM for the actual idea structuring
            llm_result = self._execute_stage_llm(stage, state)
            response += f"\n### Structured Analysis\n{llm_result.output.get('response', '')}\n"
            state.context["idea_init"] = response
            return StageResult(stage=stage, status="completed", output={"response": response})

        self._write_stage_artifact(stage.info, state, response, False)
        return StageResult(stage=stage, status="completed", output={"response": response})

    # ------------------------------------------------------------------
    # ARC Module: Experiment Execution Loop (Stage 5)
    # ------------------------------------------------------------------
    def _arc_experiment_loop(self, stage: Stage, state: PipelineState) -> StageResult:
        """Run ARC's experiment loop: LLM modifies code → sandbox executes → collect results.

        Uses IdeaClaw's SandboxExecutor (which supports subprocess and Docker).
        """
        idea_text = state.context.get("idea_text", "")
        template_dir = self.config.get("arc", {}).get("template_dir", "")
        experiment_dir = self.config.get("arc", {}).get("experiment_dir", "")

        console.print("  [cyan]🔬 ARC experiment execution loop...[/cyan]")

        if experiment_dir and Path(experiment_dir).exists():
            # Use IdeaClaw's ExperimentRunner with SandboxExecutor
            try:
                sandbox_cfg = SandboxConfig(
                    timeout_seconds=self.config.get("arc", {}).get("timeout", 7200),
                )
                runner = ExperimentRunner(
                    work_dir=Path(experiment_dir),
                    sandbox_config=sandbox_cfg,
                    max_runs=self.config.get("arc", {}).get("max_runs", ARC_MAX_RUNS),
                )

                # LLM callback for code modification
                def llm_code_fn(prompt: str, code: str) -> str:
                    return self.llm.chat_with_fallback(
                        system_prompt="You are an expert ML researcher. Modify experiment.py as instructed.",
                        user_prompt=f"{prompt}\n\nCurrent code:\n```python\n{code}\n```",
                        max_tokens=4096,
                    )

                result = runner.run(llm_code_fn=llm_code_fn)

                # Format results
                response = f"## Experiment Results\n\n"
                response += f"| Run | Metrics | Status |\n|-----|---------|--------|\n"
                for run_info in result.runs:
                    metrics_str = json.dumps(run_info.metrics, indent=None)[:100] if run_info.metrics else "N/A"
                    response += f"| {run_info.name} | {metrics_str} | {'✅' if run_info.success else '❌'} |\n"

                state.context["_experiment_results"] = {
                    r.name: r.metrics for r in result.runs if r.metrics
                }
                console.print(f"  [green]Completed {len(result.runs)} experiment runs[/green]")

            except Exception as e:
                logger.warning(f"Experiment loop failed: {e}")
                response = f"## Experiment Execution\n\nExperiment loop failed: {e}\n"
        elif template_dir and Path(template_dir).exists():
            # Direct ARC perform_experiments (requires Aider coder)
            try:
                import json as _json
                baseline_path = Path(template_dir) / "run_0" / "final_info.json"
                if baseline_path.exists():
                    baseline = _json.loads(baseline_path.read_text())
                    baseline = {k: v["means"] for k, v in baseline.items() if isinstance(v, dict) and "means" in v}
                    response = f"## Baseline Results\n\n{_json.dumps(baseline, indent=2)}\n"
                    state.context["_baseline_results"] = baseline
                    console.print(f"  [green]Loaded baseline from {template_dir}[/green]")
                else:
                    response = "## Experiment Setup\n\nNo baseline run_0/final_info.json found.\n"
            except Exception as e:
                response = f"## Experiment Setup Error\n\n{e}\n"
        else:
            # No experiment dir — fall back to LLM
            return self._execute_stage_llm(stage, state)

        self._write_stage_artifact(stage.info, state, response, False)
        return StageResult(stage=stage, status="completed", output={"response": response})

    # ------------------------------------------------------------------
    # ARC Module: LaTeX Writeup (Stage 13)
    # ------------------------------------------------------------------
    def _arc_writeup(self, stage: Stage, state: PipelineState) -> StageResult:
        """Use ARC's per-section LaTeX writeup with citation loop.

        ARC writes each section with tips, then does 2-pass refinement,
        then 20 rounds of citation enrichment via Semantic Scholar.
        """
        console.print("  [cyan]📝 ARC-style writeup (per-section + citations)...[/cyan]")

        # Collect all stage outputs into a comprehensive draft
        sections = {}
        section_map = {
            "Abstract": ["idea_init", "idea_decompose"],
            "Introduction": ["idea_init", "search_strategy"],
            "Background": ["source_collect", "source_screen"],
            "Method": ["evidence_extract", "claim_verify"],
            "Experimental Setup": ["source_screen"],
            "Results": ["evidence_synthesis", "decision_tree"],
            "Conclusion": ["evidence_synthesis", "counterargument_gen"],
        }

        draft_parts = []
        for section_name, keys in section_map.items():
            tips = ARC_SECTION_TIPS.get(section_name, "") if HAS_ARC_WRITEUP else ""
            content_parts = []
            for key in keys:
                ctx = state.context.get(key, "")
                if ctx:
                    content_parts.append(ctx)
            content = "\n\n".join(content_parts) if content_parts else f"[{section_name} content pending]"

            section_text = f"## {section_name}\n\n{content}\n"
            draft_parts.append(section_text)
            sections[section_name] = content

        # Add experiment results if available
        exp_results = state.context.get("_experiment_results")
        if exp_results:
            results_text = "## Experiment Results\n\n"
            results_text += "| Run | Metrics |\n|-----|---------|\n"
            for run_name, metrics in exp_results.items():
                results_text += f"| {run_name} | {json.dumps(metrics)[:80]} |\n"
            draft_parts.insert(-1, results_text)  # Before conclusion

        full_draft = "\n\n".join(draft_parts)

        # Use LLM to refine each section with ARC's tips
        refined_parts = []
        for section_name, keys in section_map.items():
            tips = ARC_SECTION_TIPS.get(section_name, "") if HAS_ARC_WRITEUP else ""
            raw_content = sections.get(section_name, "")

            try:
                refined = self.llm.chat_with_fallback(
                    system_prompt="You are writing a research paper. Refine this section.",
                    user_prompt=(
                        f"Section: {section_name}\n"
                        f"Writing tips: {tips}\n\n"
                        f"Raw content:\n{raw_content}\n\n"
                        f"Please refine and improve this section. "
                        f"Make it publication-ready. Include concrete data where available."
                    ),
                    max_tokens=2048,
                )
                refined_parts.append(f"## {section_name}\n\n{refined}\n")
                console.print(f"  [dim]  ✓ {section_name}[/dim]")
            except Exception as e:
                refined_parts.append(f"## {section_name}\n\n{raw_content}\n")
                logger.warning(f"Section refinement failed for {section_name}: {e}")

        response = "\n\n".join(refined_parts)
        console.print(f"  [green]Wrote {len(section_map)} sections with ARC tips[/green]")

        self._write_stage_artifact(stage.info, state, response, False)
        return StageResult(stage=stage, status="completed", output={"response": response})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_search_queries(self, strategy: str, idea: str) -> list:
        """Extract search queries from strategy text or generate from idea."""
        import re
        queries = []
        # Try to find quoted queries in strategy
        quoted = re.findall(r'["\']([^"\']{10,})["\']', strategy)
        if quoted:
            queries.extend(quoted[:5])
        # Try bullet-pointed queries
        for line in strategy.split("\n"):
            line = line.strip().lstrip("-*•0123456789. ")
            if 10 < len(line) < 100 and any(w in line.lower() for w in ["search", "query", "find", "look"]):
                queries.append(line)
        # Fallback: use idea text directly
        if not queries:
            # Split idea into 2-3 search queries
            words = idea.split()
            if len(words) > 8:
                queries.append(" ".join(words[:8]))
                queries.append(" ".join(words[4:12]))
            else:
                queries.append(idea)
        return queries[:5]

    def _write_stage_artifact(self, info, state, response, json_mode):
        """Write stage output as artifact file."""
        artifact_dir = _ARTIFACT_DIR_MAP.get(info.prompt_key, ".")
        artifact_base = state.run_dir / artifact_dir
        artifact_base.mkdir(parents=True, exist_ok=True)

        if json_mode:
            try:
                parsed = json.loads(response)
                write_json(artifact_base / f"{info.prompt_key}.json", parsed)
            except json.JSONDecodeError:
                (artifact_base / f"{info.prompt_key}.md").write_text(
                    response, encoding="utf-8"
                )
        else:
            (artifact_base / f"{info.prompt_key}.md").write_text(
                response, encoding="utf-8"
            )

    def _write_final_pack(self, state: PipelineState) -> None:
        """Write the final pack using PackBuilder + TrustReviewer + Exporter."""
        from ideaclaw.pack.builder import PackBuilder
        from ideaclaw.pack.trust_review import TrustReviewer
        from ideaclaw.export import Exporter

        idea_text = state.context.get("idea_text", "")
        pack_type_str = state.context.get("pack_type", "decision")
        if pack_type_str == "auto":
            pack_type_str = "decision"

        # 1. Load deliverable template first (needed for trust review)
        review_form = None
        if HAS_TEMPLATES:
            profile_id = self.config.get("scenario_id", "")
            tpl_loader = TemplateLoader()
            if tpl_loader.has_template(profile_id):
                tpl_content = tpl_loader.get_template_content(profile_id)
                tpl_sections = tpl_loader.get_sections(profile_id)
                tpl_format = tpl_loader.get_format(profile_id)
                review_form = tpl_loader.get_review_form(profile_id)
                console.print(
                    f"  [cyan]📋 Template: {profile_id} ({tpl_format}, "
                    f"{len(tpl_sections)} sections, tier={tpl_loader.get_tier(profile_id)})[/cyan]"
                )

        # 2. Trust review (with domain-specific review_form if available)
        draft = state.context.get("pack_draft", state.context.get("export_publish", ""))
        reviewer = TrustReviewer(self.config)
        trust_result = reviewer.review(
            draft=draft,
            idea_text=idea_text,
            review_form=review_form,
        )
        console.print(
            f"\n  [bold]Trust Review:[/bold] PQS={trust_result.overall_score:.2f} "
            f"[{'green' if trust_result.verdict == 'PASS' else 'yellow' if trust_result.verdict == 'REVISE' else 'red'}]"
            f"{trust_result.verdict}"
            f"[/{'green' if trust_result.verdict == 'PASS' else 'yellow' if trust_result.verdict == 'REVISE' else 'red'}]"
        )

        # 3. Build pack with templates
        pipeline_ctx = {
            "idea": idea_text,
            "pack_type": pack_type_str,
            "run_id": state.run_id,
            "draft": draft,
            "conclusion": state.context.get("evidence_synthesis", draft),
            "reasoning": state.context.get("evidence_synthesis", ""),
            "synthesis": state.context.get("evidence_synthesis", ""),
            "counterarguments": self._parse_list(state.context.get("counterargument_gen", "")),
            "uncertainties": self._parse_list(state.context.get("evidence_gate", "")),
            "action_items": self._parse_list(state.context.get("pack_outline", "")),
            "sources": self._parse_sources(state.context.get("source_collect", "")),
            "trust_review": trust_result,
            "decomposition": state.context.get("idea_decompose", ""),
            "decision_tree": state.context.get("decision_tree", ""),
        }

        # 3b. Inject deliverable template context
        if HAS_TEMPLATES and tpl_loader.has_template(self.config.get("scenario_id", "")):
            pipeline_ctx["deliverable_template"] = tpl_content or ""
            pipeline_ctx["deliverable_sections"] = tpl_sections
            pipeline_ctx["deliverable_format"] = tpl_format
            pipeline_ctx["review_form"] = review_form or {}
            pipeline_ctx["template_tier"] = tpl_loader.get_tier(profile_id)

        builder = PackBuilder(self.config)
        pack_data = builder.build(pipeline_ctx)

        # 3. Add trust review to pack_data for export
        pack_data["trust_review"] = trust_result.to_dict()

        # 4. Export
        exporter = Exporter(self.config)
        exported = exporter.export_all(pack_data, state.run_dir)

        for p in exported:
            console.print(f"  [bold green]📦 {p.name}[/bold green] → {p}")

    def _parse_list(self, text: str) -> list:
        """Parse a text output into a list of items."""
        if not text:
            return []
        items = []
        for line in text.split("\n"):
            line = line.strip().lstrip("-*0123456789. ")
            if line and len(line) > 5:
                items.append(line)
        return items[:20]

    def _parse_sources(self, text: str) -> list:
        """Parse source collection output into structured sources."""
        import re
        if not text:
            return []
        sources = []
        for line in text.split("\n"):
            url_match = re.search(r'(https?://\S+)', line)
            if url_match:
                sources.append({"title": line.strip()[:100], "url": url_match.group(1)})
            elif line.strip() and len(line.strip()) > 10:
                sources.append({"title": line.strip()[:100], "url": ""})
        return sources[:30]

    def _request_approval(self, stage: Stage) -> bool:
        """Request human approval at a gate stage."""
        console.print(f"  [yellow]⏸  Gate stage — approval required[/yellow]")

        if self.auto_approve:
            console.print(f"  [dim]Auto-approved[/dim]")
            return True

        answer = console.input("  [bold]Approve? (y/n): [/bold]").strip().lower()
        return answer in ("y", "yes")

    def _print_header(self, state: PipelineState) -> None:
        """Print pipeline run header."""
        console.print(f"\n[bold blue]🦞 IdeaClaw Pipeline[/bold blue]")
        console.print(f"[dim]Run ID:    {state.run_id}[/dim]")
        console.print(f"[dim]Output:    {state.run_dir}[/dim]")
        console.print(f"[dim]Idea:      {state.context.get('idea_text', '?')}[/dim]")
        console.print(f"[dim]Pack type: {state.context.get('pack_type', 'auto')}[/dim]")
        console.rule()

    def _print_summary(self, state: PipelineState) -> None:
        """Print pipeline completion summary."""
        console.print()
        console.rule("[bold green]Pipeline Complete")

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", width=3)
        table.add_column("Stage", min_width=20)
        table.add_column("Status", min_width=10)
        table.add_column("Time", min_width=8)

        for stage in STAGE_ORDER:
            result = state.stage_results.get(stage.info.name)
            if result:
                status_style = "green" if result.status == "completed" else "red"
                table.add_row(
                    str(stage.info.number),
                    stage.info.name,
                    f"[{status_style}]{result.status}[/{status_style}]",
                    f"{result.duration_sec:.1f}s",
                )

        console.print(table)

    @staticmethod
    def _ensure_run_layout(run_dir: Path) -> None:
        """Create standard subdirectories for a run."""
        for subdir in ["evidence", "evidence/extracted", "reasoning", "trust"]:
            (run_dir / subdir).mkdir(parents=True, exist_ok=True)

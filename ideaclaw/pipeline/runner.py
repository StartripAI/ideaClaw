"""Main pipeline runner — orchestrates all 15 stages with real LLM calls."""

from __future__ import annotations

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
        """Execute a single pipeline stage by calling the LLM."""
        info = stage.info

        # Build prompt context from accumulated state
        prompt_vars = dict(state.context)

        system_prompt = self.prompts.get_system_prompt(info.prompt_key)
        user_prompt = self.prompts.get_user_prompt(info.prompt_key, **prompt_vars)
        json_mode = self.prompts.is_json_mode(info.prompt_key)
        max_tokens = self.prompts.get_max_tokens(info.prompt_key)

        # Call LLM
        response = self.llm.chat_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )

        # Write stage artifact
        artifact_dir = _ARTIFACT_DIR_MAP.get(info.prompt_key, ".")
        artifact_base = state.run_dir / artifact_dir
        artifact_base.mkdir(parents=True, exist_ok=True)

        if json_mode:
            # Try to parse JSON response
            try:
                parsed = json.loads(response)
                write_json(artifact_base / f"{info.prompt_key}.json", parsed)
            except json.JSONDecodeError:
                # Write as text if not valid JSON
                (artifact_base / f"{info.prompt_key}.md").write_text(
                    response, encoding="utf-8"
                )
        else:
            (artifact_base / f"{info.prompt_key}.md").write_text(
                response, encoding="utf-8"
            )

        return StageResult(
            stage=stage,
            status="completed",
            output={"response": response},
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

        # 1. Trust review
        draft = state.context.get("pack_draft", state.context.get("export_publish", ""))
        reviewer = TrustReviewer(self.config)
        trust_result = reviewer.review(
            draft=draft,
            idea_text=idea_text,
        )
        console.print(
            f"\n  [bold]Trust Review:[/bold] PQS={trust_result.overall_score:.2f} "
            f"[{'green' if trust_result.verdict == 'PASS' else 'yellow' if trust_result.verdict == 'REVISE' else 'red'}]"
            f"{trust_result.verdict}"
            f"[/{'green' if trust_result.verdict == 'PASS' else 'yellow' if trust_result.verdict == 'REVISE' else 'red'}]"
        )

        # 2. Build pack with templates
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

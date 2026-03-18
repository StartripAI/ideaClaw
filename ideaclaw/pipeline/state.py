"""Pipeline state machine — tracks progress, checkpoints, and artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from ideaclaw.pipeline.stages import Stage, STAGE_ORDER


@dataclass
class StageResult:
    """Result of executing a single stage."""
    stage: Stage
    status: str  # "completed" | "failed" | "skipped" | "gate_rejected"
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_sec: float = 0.0


@dataclass
class PipelineState:
    """Mutable state for a pipeline run."""
    run_id: str
    run_dir: Path
    current_stage_idx: int = 0
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)  # Accumulated data across stages
    status: str = "initialized"  # initialized | running | completed | failed | paused

    @property
    def current_stage(self) -> Stage:
        return STAGE_ORDER[self.current_stage_idx]

    @property
    def is_complete(self) -> bool:
        return self.current_stage_idx >= len(STAGE_ORDER)

    def advance(self) -> None:
        """Move to the next stage."""
        self.current_stage_idx += 1

    def rollback_to(self, stage_number: int) -> None:
        """Roll back to a specific stage number."""
        for idx, stage in enumerate(STAGE_ORDER):
            if stage.info.number == stage_number:
                self.current_stage_idx = idx
                return
        raise ValueError(f"No stage with number {stage_number}")

    def record_result(self, result: StageResult) -> None:
        """Record the result of a stage execution."""
        self.stage_results[result.stage.info.name] = result

    def save_checkpoint(self) -> None:
        """Save state to checkpoint file."""
        checkpoint_path = self.run_dir / "checkpoint.json"
        self.run_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "run_id": self.run_id,
            "current_stage_idx": self.current_stage_idx,
            "status": self.status,
            "stage_results": {
                name: {
                    "stage": r.stage.info.name,
                    "status": r.status,
                    "error": r.error,
                    "duration_sec": r.duration_sec,
                }
                for name, r in self.stage_results.items()
            },
        }

        checkpoint_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load_checkpoint(cls, run_dir: Path) -> Optional["PipelineState"]:
        """Load state from checkpoint file."""
        checkpoint_path = run_dir / "checkpoint.json"
        if not checkpoint_path.exists():
            return None

        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        state = cls(
            run_id=data["run_id"],
            run_dir=run_dir,
            current_stage_idx=data["current_stage_idx"],
            status=data["status"],
        )
        return state

"""Version control for orchestrator — AR-style commit/revert.

Tracks each iteration's draft, scores, and decisions.
Provides revert capability and diff history.
"""

from __future__ import annotations

import difflib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VersionEntry:
    """A single version in the history."""
    iteration: int
    score: float
    scores_detail: Dict[str, float]
    accepted: bool
    timestamp: str
    draft_hash: str = ""
    diff_lines: int = 0


class Versioning:
    """AR-style version control: commit accepted drafts, revert rejected ones.

    Maintains a linear history of accepted drafts with diffs,
    allowing rollback to any previous version.

    Usage:
        v = Versioning(run_dir=Path("runs/icml_20260318"))
        v.commit("run1", 0, draft_text, 0.85, {"novelty": 0.9})
        v.commit("run1", 1, better_draft, 0.90, {"novelty": 0.95})
        
        # Revert iteration 2 (failed)
        v.revert("run1", 2)
        
        # Get best version
        best = v.get_best("run1")
    """

    def __init__(self, run_dir: Optional[Path] = None):
        self.run_dir = run_dir or Path.home() / ".ideaclaw" / "versions"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._history: Dict[str, List[VersionEntry]] = {}
        self._drafts: Dict[str, Dict[int, str]] = {}  # run_id → {iter: draft}

    def _run_path(self, run_id: str) -> Path:
        p = self.run_dir / run_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def commit(
        self,
        run_id: str,
        iteration: int,
        draft: str,
        score: float,
        scores_detail: Dict[str, float],
    ) -> str:
        """Commit an accepted draft version.

        Args:
            run_id: The run identifier.
            iteration: Iteration number.
            draft: The draft text.
            score: Composite score.
            scores_detail: Per-criterion scores.

        Returns:
            Path to the saved draft file.
        """
        run_path = self._run_path(run_id)

        # Save draft
        draft_path = run_path / f"v{iteration:03d}.md"
        draft_path.write_text(draft, encoding="utf-8")

        # Compute diff from previous version
        prev_draft = self._get_latest_draft(run_id)
        diff_lines = 0
        if prev_draft is not None:
            diff = list(difflib.unified_diff(
                prev_draft.splitlines(keepends=True),
                draft.splitlines(keepends=True),
                fromfile=f"v{iteration-1:03d}", tofile=f"v{iteration:03d}",
            ))
            diff_lines = len([l for l in diff if l.startswith('+') or l.startswith('-')])
            diff_path = run_path / f"diff_{iteration:03d}.patch"
            diff_path.write_text("".join(diff), encoding="utf-8")

        # Record version
        entry = VersionEntry(
            iteration=iteration,
            score=score,
            scores_detail=scores_detail,
            accepted=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
            draft_hash=str(hash(draft))[-8:],
            diff_lines=diff_lines,
        )

        self._history.setdefault(run_id, []).append(entry)
        self._drafts.setdefault(run_id, {})[iteration] = draft

        # Save history
        self._save_history(run_id)

        return str(draft_path)

    def revert(self, run_id: str, iteration: int) -> Optional[str]:
        """Revert a rejected iteration — rolls back to previous accepted version.

        Args:
            run_id: The run identifier.
            iteration: The iteration that was rejected.

        Returns:
            The reverted-to draft text, or None if no previous version.
        """
        # Record the revert
        entry = VersionEntry(
            iteration=iteration,
            score=0.0,
            scores_detail={},
            accepted=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._history.setdefault(run_id, []).append(entry)
        self._save_history(run_id)

        return self._get_latest_draft(run_id)

    def get_best(self, run_id: str) -> Optional[str]:
        """Get the draft from the best-scoring accepted version."""
        history = self._history.get(run_id, [])
        accepted = [e for e in history if e.accepted]
        if not accepted:
            return None

        best = max(accepted, key=lambda e: e.score)
        return self._drafts.get(run_id, {}).get(best.iteration)

    def get_version(self, run_id: str, iteration: int) -> Optional[str]:
        """Get draft text for a specific iteration."""
        drafts = self._drafts.get(run_id, {})
        if iteration in drafts:
            return drafts[iteration]

        # Try loading from disk
        draft_path = self._run_path(run_id) / f"v{iteration:03d}.md"
        if draft_path.exists():
            return draft_path.read_text(encoding="utf-8")
        return None

    def get_history(self, run_id: str) -> List[Dict[str, Any]]:
        """Get iteration history for a run."""
        return [
            {
                "iteration": e.iteration,
                "score": e.score,
                "accepted": e.accepted,
                "diff_lines": e.diff_lines,
                "timestamp": e.timestamp,
            }
            for e in self._history.get(run_id, [])
        ]

    def get_diff(self, run_id: str, from_iter: int, to_iter: int) -> str:
        """Get unified diff between two iterations."""
        draft_a = self.get_version(run_id, from_iter) or ""
        draft_b = self.get_version(run_id, to_iter) or ""

        diff = difflib.unified_diff(
            draft_a.splitlines(keepends=True),
            draft_b.splitlines(keepends=True),
            fromfile=f"v{from_iter:03d}", tofile=f"v{to_iter:03d}",
        )
        return "".join(diff)

    def evolution_report(self, run_id: str) -> str:
        """Generate a markdown evolution report showing score progression."""
        history = self._history.get(run_id, [])
        if not history:
            return f"# Evolution Report: {run_id}\n\nNo iterations recorded."

        lines = [
            f"# Evolution Report: {run_id}",
            "",
            "| Iter | Score | Status | Diff Lines | Best Scores |",
            "|---|---|---|---|---|",
        ]

        best_score = 0.0
        for e in history:
            status = "✅ Accept" if e.accepted else "❌ Revert"
            if e.accepted and e.score > best_score:
                best_score = e.score
                status += " ★"
            detail = ", ".join(f"{k}={v:.2f}" for k, v in sorted(e.scores_detail.items())[:3])
            lines.append(f"| {e.iteration} | {e.score:.3f} | {status} | {e.diff_lines} | {detail} |")

        accepted = [e for e in history if e.accepted]
        reverted = [e for e in history if not e.accepted]
        lines.extend([
            "",
            f"**Summary**: {len(accepted)} accepted, {len(reverted)} reverted, best={best_score:.3f}",
        ])

        return "\n".join(lines)

    def cleanup(self, run_id: str) -> None:
        """Remove all version data for a run."""
        run_path = self._run_path(run_id)
        if run_path.exists():
            shutil.rmtree(run_path)
        self._history.pop(run_id, None)
        self._drafts.pop(run_id, None)

    # ---- Internal ----

    def _get_latest_draft(self, run_id: str) -> Optional[str]:
        """Get the most recent accepted draft."""
        drafts = self._drafts.get(run_id, {})
        history = self._history.get(run_id, [])
        accepted = [e for e in history if e.accepted]
        if accepted:
            latest = max(accepted, key=lambda e: e.iteration)
            return drafts.get(latest.iteration)
        return None

    def _save_history(self, run_id: str) -> None:
        """Persist history to disk."""
        run_path = self._run_path(run_id)
        history = self._history.get(run_id, [])
        data = [
            {
                "iteration": e.iteration,
                "score": e.score,
                "scores_detail": e.scores_detail,
                "accepted": e.accepted,
                "timestamp": e.timestamp,
                "draft_hash": e.draft_hash,
                "diff_lines": e.diff_lines,
            }
            for e in history
        ]
        (run_path / "history.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

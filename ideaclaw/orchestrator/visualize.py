"""Experiment visualization — charts and HTML reports for research runs.

Features:
  - Score progression line charts (iteration × dimension)
  - Dimension radar charts (multi-axis comparison)
  - Domain heatmap (scenario × dimension scores)
  - Self-contained HTML report with embedded base64 images
  - Graceful fallback: ASCII charts when matplotlib unavailable

Usage:
    from ideaclaw.orchestrator.visualize import RunVisualizer

logger = logging.getLogger(__name__)

__all__ = ['ChartResult', 'RunVisualizer']
    viz = RunVisualizer()
    viz.plot_score_progression(state, output_path)
    viz.generate_html_report(state, output_dir)
"""

from __future__ import annotations
import logging

import base64
import html
import io
import json
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try matplotlib — graceful fallback to ASCII
try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


@dataclass
class ChartResult:
    """Result from a chart generation."""
    path: Optional[Path] = None
    base64_png: str = ""
    ascii_fallback: str = ""

    @property
    def available(self) -> bool:
        return bool(self.path or self.base64_png or self.ascii_fallback)


class RunVisualizer:
    """Visualize research run results."""

    # Color palette (colorblind-friendly)
    COLORS = [
        "#0072B2", "#E69F00", "#009E73", "#CC79A7",
        "#56B4E9", "#D55E00", "#F0E442", "#000000",
    ]

    def __init__(self, dpi: int = 150, figsize: Tuple[float, float] = (8, 5)):
        self.dpi = dpi
        self.figsize = figsize

    # ---- Score Progression ----

    def plot_score_progression(
        self,
        iterations: List[Dict[str, Any]],
        output_path: Optional[Path] = None,
    ) -> ChartResult:
        """Plot score over iterations as a line chart.

        Args:
            iterations: List of dicts with 'scores' (dim→float) and 'composite'.
            output_path: Optional path to save PNG.

        Returns:
            ChartResult with path or base64 or ASCII.
        """
        if not iterations:
            return ChartResult(ascii_fallback="(no iterations to plot)")

        # Extract data
        composites = [it.get("composite", 0) for it in iterations]
        dims = {}
        for it in iterations:
            for dim, val in it.get("scores", {}).items():
                dims.setdefault(dim, []).append(val)

        if HAS_MPL:
            return self._mpl_progression(composites, dims, output_path)
        return self._ascii_progression(composites, dims)

    def _mpl_progression(
        self, composites: list, dims: dict, output_path: Optional[Path],
    ) -> ChartResult:
        fig, ax = plt.subplots(figsize=self.figsize)
        x = list(range(1, len(composites) + 1))

        # Plot composite as thick line
        ax.plot(x, composites, "k-o", linewidth=2.5, markersize=8,
                label="Composite", zorder=10)

        # Plot per-dimension as thinner lines
        for i, (dim, vals) in enumerate(sorted(dims.items())):
            color = self.COLORS[i % len(self.COLORS)]
            ax.plot(x[:len(vals)], vals, "-s", color=color, linewidth=1.2,
                    markersize=5, alpha=0.7, label=dim.capitalize())

        ax.set_xlabel("Iteration", fontsize=12)
        ax.set_ylabel("Score", fontsize=12)
        ax.set_title("Score Progression", fontsize=14, fontweight="bold")
        ax.set_ylim(-0.05, 1.05)
        ax.legend(loc="lower right", fontsize=9, ncol=2)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        return self._save_fig(fig, output_path)

    def _ascii_progression(self, composites: list, dims: dict) -> ChartResult:
        lines = ["Score Progression", "=" * 40]
        for i, c in enumerate(composites):
            bar = "█" * int(c * 30)
            lines.append(f"  Iter {i+1}: {bar} {c:.2f}")
        return ChartResult(ascii_fallback="\n".join(lines))

    # ---- Dimension Radar ----

    def plot_dimension_radar(
        self,
        scores: Dict[str, float],
        output_path: Optional[Path] = None,
        title: str = "Evaluation Radar",
    ) -> ChartResult:
        """Plot a radar chart of dimension scores."""
        if not scores:
            return ChartResult(ascii_fallback="(no scores)")

        if HAS_MPL:
            return self._mpl_radar(scores, output_path, title)
        return self._ascii_radar(scores, title)

    def _mpl_radar(
        self, scores: dict, output_path: Optional[Path], title: str,
    ) -> ChartResult:
        labels = list(scores.keys())
        values = list(scores.values())
        n = len(labels)

        angles = [i * 2 * math.pi / n for i in range(n)]
        values_closed = values + [values[0]]
        angles_closed = angles + [angles[0]]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        ax.fill(angles_closed, values_closed, alpha=0.25, color=self.COLORS[0])
        ax.plot(angles_closed, values_closed, "o-", color=self.COLORS[0],
                linewidth=2, markersize=6)

        ax.set_xticks(angles)
        ax.set_xticklabels([l.capitalize() for l in labels], fontsize=10)
        ax.set_ylim(0, 1)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
        fig.tight_layout()

        return self._save_fig(fig, output_path)

    def _ascii_radar(self, scores: dict, title: str) -> ChartResult:
        lines = [title, "-" * 40]
        for dim, val in sorted(scores.items()):
            bar = "█" * int(val * 30)
            lines.append(f"  {dim:15s} {bar} {val:.2f}")
        return ChartResult(ascii_fallback="\n".join(lines))

    # ---- Domain Heatmap ----

    def plot_domain_heatmap(
        self,
        results: List[Dict[str, Any]],
        output_path: Optional[Path] = None,
    ) -> ChartResult:
        """Plot scenario × dimension heatmap.

        Args:
            results: List of dicts with 'scenario_id' and 'scores'.
        """
        if not results:
            return ChartResult(ascii_fallback="(no results)")

        scenarios = [r.get("scenario_id", f"s{i}") for i, r in enumerate(results)]
        all_dims = set()
        for r in results:
            all_dims.update(r.get("scores", {}).keys())
        dims = sorted(all_dims)

        if not dims:
            return ChartResult(ascii_fallback="(no dimensions)")

        matrix = []
        for r in results:
            row = [r.get("scores", {}).get(d, 0) for d in dims]
            matrix.append(row)

        if HAS_MPL:
            return self._mpl_heatmap(matrix, scenarios, dims, output_path)
        return self._ascii_heatmap(matrix, scenarios, dims)

    def _mpl_heatmap(
        self, matrix: list, scenarios: list, dims: list,
        output_path: Optional[Path],
    ) -> ChartResult:
        import numpy as np
        data = np.array(matrix)

        fig, ax = plt.subplots(figsize=(max(8, len(dims) * 1.2), max(4, len(scenarios) * 0.5)))
        im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")

        ax.set_xticks(range(len(dims)))
        ax.set_xticklabels([d.capitalize() for d in dims], rotation=45, ha="right", fontsize=9)
        ax.set_yticks(range(len(scenarios)))
        ax.set_yticklabels(scenarios, fontsize=9)

        # Annotate cells
        for i in range(len(scenarios)):
            for j in range(len(dims)):
                val = data[i, j]
                color = "white" if val < 0.4 or val > 0.8 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        color=color, fontsize=8)

        fig.colorbar(im, ax=ax, shrink=0.8, label="Score")
        ax.set_title("Scenario × Dimension Heatmap", fontsize=14, fontweight="bold")
        fig.tight_layout()

        return self._save_fig(fig, output_path)

    def _ascii_heatmap(self, matrix, scenarios, dims) -> ChartResult:
        lines = ["Scenario × Dimension Heatmap", "=" * 60]
        header = f"{'Scenario':20s} " + " ".join(f"{d[:6]:>6s}" for d in dims)
        lines.append(header)
        lines.append("-" * len(header))
        for i, s in enumerate(scenarios):
            row = " ".join(f"{matrix[i][j]:6.2f}" for j in range(len(dims)))
            lines.append(f"{s:20s} {row}")
        return ChartResult(ascii_fallback="\n".join(lines))

    # ---- HTML Report ----

    def generate_html_report(
        self,
        state: Dict[str, Any],
        output_dir: Path,
        title: str = "IdeaClaw Research Run Report",
    ) -> Path:
        """Generate a self-contained HTML report with embedded charts.

        Args:
            state: Run state dict with 'iterations', 'profile_id', 'best_score', etc.
            output_dir: Directory to save report.
            title: Report title.

        Returns:
            Path to the generated HTML file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "report.html"

        iterations = state.get("iterations", [])
        profile_id = state.get("profile_id", "unknown")
        best_score = state.get("best_score", 0)
        status = state.get("status", "unknown")

        # Generate charts
        progression = self.plot_score_progression(iterations)
        best_scores = iterations[-1].get("scores", {}) if iterations else {}
        radar = self.plot_dimension_radar(best_scores)

        # Build HTML
        charts_html = ""
        if progression.base64_png:
            charts_html += f'<img src="data:image/png;base64,{progression.base64_png}" alt="Score Progression" style="max-width:100%;">\n'
        elif progression.ascii_fallback:
            charts_html += f"<pre>{html.escape(progression.ascii_fallback)}</pre>\n"

        if radar.base64_png:
            charts_html += f'<img src="data:image/png;base64,{radar.base64_png}" alt="Radar" style="max-width:100%;">\n'
        elif radar.ascii_fallback:
            charts_html += f"<pre>{html.escape(radar.ascii_fallback)}</pre>\n"

        # Iteration details
        iter_rows = ""
        for i, it in enumerate(iterations):
            scores = it.get("scores", {})
            composite = it.get("composite", 0)
            accepted = "✅" if it.get("accepted", False) else "❌"
            cols = " ".join(f"<td>{scores.get(d, 0):.2f}</td>" for d in sorted(scores.keys()))
            iter_rows += f"<tr><td>{i+1}</td><td>{composite:.3f}</td><td>{accepted}</td>{cols}</tr>\n"

        dim_headers = ""
        if iterations:
            dim_headers = " ".join(f"<th>{d.capitalize()}</th>"
                                   for d in sorted(iterations[0].get("scores", {}).keys()))

        report_html = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>{html.escape(title)}</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                       max-width: 900px; margin: 40px auto; padding: 0 20px;
                       background: #fafafa; color: #333; }}
                h1 {{ color: #1a1a2e; border-bottom: 3px solid #0072B2; padding-bottom: 10px; }}
                h2 {{ color: #16213e; }}
                .summary {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                           padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .summary .score {{ font-size: 2em; font-weight: bold; color: #0072B2; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: center; }}
                th {{ background: #0072B2; color: white; }}
                tr:nth-child(even) {{ background: #f8f8f8; }}
                .charts {{ text-align: center; margin: 20px 0; }}
                .charts img {{ border: 1px solid #ddd; border-radius: 4px; margin: 10px; }}
                pre {{ background: #f4f4f4; padding: 15px; border-radius: 4px;
                      overflow-x: auto; font-size: 13px; }}
                .badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px;
                         font-size: 0.85em; font-weight: bold; }}
                .badge-ok {{ background: #d4edda; color: #155724; }}
                .badge-fail {{ background: #f8d7da; color: #721c24; }}
                footer {{ margin-top: 40px; text-align: center; color: #999; font-size: 0.85em; }}
            </style>
        </head>
        <body>
            <h1>📊 {html.escape(title)}</h1>

            <div class="summary">
                <p><strong>Profile:</strong> {html.escape(profile_id)}</p>
                <p><strong>Status:</strong>
                    <span class="badge {'badge-ok' if status == 'completed' else 'badge-fail'}">
                        {html.escape(status.upper())}
                    </span>
                </p>
                <p><strong>Iterations:</strong> {len(iterations)}</p>
                <p><strong>Best Score:</strong> <span class="score">{best_score:.3f}</span></p>
            </div>

            <h2>📈 Score Progression</h2>
            <div class="charts">
                {charts_html}
            </div>

            <h2>📋 Iteration Details</h2>
            <table>
                <tr><th>#</th><th>Composite</th><th>Accepted</th>{dim_headers}</tr>
                {iter_rows}
            </table>

            <footer>
                Generated by IdeaClaw • Profile: {html.escape(profile_id)}
            </footer>
        </body>
        </html>
        """)

        report_path.write_text(report_html, encoding="utf-8")
        return report_path

    # ---- Helpers ----

    def _save_fig(self, fig, output_path: Optional[Path]) -> ChartResult:
        """Save matplotlib figure to file and/or base64."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")

        result = ChartResult(base64_png=b64)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                buf.seek(0)
                f.write(buf.read())
            result.path = output_path

        return result

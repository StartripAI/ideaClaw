"""Experiment visualization — generate plots and tables from results.

Surpasses ARC's visualize.py by providing:
  - Pure-Python matplotlib generation (no external deps beyond matplotlib)
  - Metric trend plots, ablation tables, comparison bar charts
  - LaTeX-ready table output
  - Self-contained HTML report generation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MetricSeries:
    """A time series of metric values across experiment runs."""
    name: str
    values: List[float]
    labels: List[str]  # run IDs or descriptions
    direction: str = "minimize"  # minimize | maximize
    unit: str = ""


@dataclass
class AblationRow:
    """A single row in an ablation table."""
    variant: str
    metrics: Dict[str, float]
    delta: Dict[str, float] = field(default_factory=dict)
    is_baseline: bool = False


class ExperimentVisualizer:
    """Generate visualizations from experiment results.

    Usage:
        viz = ExperimentVisualizer()
        viz.add_metric_series("val_bpb", [1.5, 1.4, 1.3, 1.2], ["run1", "run2", "run3", "run4"])
        viz.add_ablation_row("baseline", {"val_bpb": 1.5, "speed": 100}, is_baseline=True)
        viz.add_ablation_row("+ attention", {"val_bpb": 1.3, "speed": 95})
        
        viz.plot_metric_trends(output_dir)
        viz.generate_ablation_table(output_dir)
        viz.generate_html_report(output_dir)
    """

    def __init__(self):
        self.series: List[MetricSeries] = []
        self.ablation_rows: List[AblationRow] = []
        self.comparisons: List[Tuple[str, Dict[str, float]]] = []

    def add_metric_series(
        self,
        name: str,
        values: List[float],
        labels: List[str],
        direction: str = "minimize",
        unit: str = "",
    ) -> None:
        """Add a metric time series."""
        self.series.append(MetricSeries(
            name=name, values=values, labels=labels,
            direction=direction, unit=unit,
        ))

    def add_ablation_row(
        self,
        variant: str,
        metrics: Dict[str, float],
        is_baseline: bool = False,
    ) -> None:
        """Add a row to the ablation table."""
        self.ablation_rows.append(AblationRow(
            variant=variant, metrics=metrics, is_baseline=is_baseline,
        ))

    def add_comparison(self, name: str, metrics: Dict[str, float]) -> None:
        """Add a system/method for comparison bar chart."""
        self.comparisons.append((name, metrics))

    def plot_metric_trends(self, output_dir: Path) -> List[str]:
        """Generate metric trend plots using matplotlib.

        Returns list of saved file paths.
        """
        saved = []
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            for s in self.series:
                fig, ax = plt.subplots(figsize=(10, 5))
                ax.plot(range(len(s.values)), s.values, "o-", linewidth=2, markersize=6)
                ax.set_xlabel("Run", fontsize=12)
                ylabel = f"{s.name}" + (f" ({s.unit})" if s.unit else "")
                ax.set_ylabel(ylabel, fontsize=12)
                ax.set_title(f"{s.name} Trend ({s.direction})", fontsize=14)
                ax.set_xticks(range(len(s.labels)))
                ax.set_xticklabels(s.labels, rotation=45, ha="right")
                ax.grid(True, alpha=0.3)

                # Highlight best value
                best_idx = (s.values.index(min(s.values)) if s.direction == "minimize"
                            else s.values.index(max(s.values)))
                ax.plot(best_idx, s.values[best_idx], "*", markersize=15,
                        color="gold", zorder=5)

                fig.tight_layout()
                path = output_dir / f"trend_{s.name}.png"
                fig.savefig(path, dpi=150)
                plt.close(fig)
                saved.append(str(path))

        except ImportError:
            # matplotlib not available — generate text-based fallback
            for s in self.series:
                path = output_dir / f"trend_{s.name}.txt"
                lines = [f"Trend: {s.name} ({s.direction})"]
                for label, val in zip(s.labels, s.values):
                    bar = "#" * int(val * 20)
                    lines.append(f"  {label:>20s} | {val:8.4f} | {bar}")
                path.write_text("\n".join(lines))
                saved.append(str(path))

        return saved

    def plot_comparison_bars(self, output_dir: Path, metric: str) -> str:
        """Generate comparison bar chart for a specific metric."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            names = [c[0] for c in self.comparisons]
            values = [c[1].get(metric, 0) for c in self.comparisons]

            fig, ax = plt.subplots(figsize=(10, 5))
            colors = plt.cm.viridis([i / max(1, len(names) - 1) for i in range(len(names))])
            bars = ax.bar(range(len(names)), values, color=colors)

            # Add value labels on bars
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{val:.4f}", ha="center", va="bottom", fontsize=9)

            ax.set_xticks(range(len(names)))
            ax.set_xticklabels(names, rotation=45, ha="right")
            ax.set_ylabel(metric, fontsize=12)
            ax.set_title(f"Comparison: {metric}", fontsize=14)
            ax.grid(True, axis="y", alpha=0.3)
            fig.tight_layout()

            path = output_dir / f"comparison_{metric}.png"
            fig.savefig(path, dpi=150)
            plt.close(fig)
            return str(path)

        except ImportError:
            path = output_dir / f"comparison_{metric}.txt"
            lines = [f"Comparison: {metric}"]
            for name, metrics in self.comparisons:
                val = metrics.get(metric, 0)
                lines.append(f"  {name:>30s} | {val:.4f}")
            path.write_text("\n".join(lines))
            return str(path)

    def generate_ablation_table(
        self,
        output_dir: Optional[Path] = None,
        format: str = "markdown",
    ) -> str:
        """Generate ablation study table.

        Args:
            output_dir: Optional directory to save the table.
            format: 'markdown' or 'latex'.

        Returns:
            Table as string.
        """
        if not self.ablation_rows:
            return ""

        # Find baseline
        baseline = next((r for r in self.ablation_rows if r.is_baseline), self.ablation_rows[0])

        # Compute deltas
        all_metrics = sorted(set(k for r in self.ablation_rows for k in r.metrics))
        for row in self.ablation_rows:
            for m in all_metrics:
                if m in row.metrics and m in baseline.metrics:
                    row.delta[m] = row.metrics[m] - baseline.metrics[m]

        if format == "latex":
            return self._ablation_latex(all_metrics, output_dir)
        else:
            return self._ablation_markdown(all_metrics, output_dir)

    def _ablation_markdown(self, metrics: List[str], output_dir: Optional[Path]) -> str:
        lines = ["## Ablation Study", ""]
        header = "| Variant | " + " | ".join(metrics) + " |"
        sep = "|---|" + "|".join(["---"] * len(metrics)) + "|"
        lines.extend([header, sep])

        for row in self.ablation_rows:
            cells = []
            for m in metrics:
                val = row.metrics.get(m, 0)
                delta = row.delta.get(m, 0)
                if row.is_baseline:
                    cells.append(f"{val:.4f}")
                else:
                    sign = "+" if delta > 0 else ""
                    cells.append(f"{val:.4f} ({sign}{delta:.4f})")
            tag = " ★" if row.is_baseline else ""
            lines.append(f"| {row.variant}{tag} | " + " | ".join(cells) + " |")

        table = "\n".join(lines)
        if output_dir:
            (output_dir / "ablation.md").write_text(table)
        return table

    def _ablation_latex(self, metrics: List[str], output_dir: Optional[Path]) -> str:
        cols = "l" + "r" * len(metrics)
        lines = [
            f"\\begin{{tabular}}{{{cols}}}",
            "\\toprule",
            "Variant & " + " & ".join(metrics) + " \\\\",
            "\\midrule",
        ]
        for row in self.ablation_rows:
            cells = []
            for m in metrics:
                val = row.metrics.get(m, 0)
                if row.is_baseline:
                    cells.append(f"{val:.4f}")
                else:
                    best_in_col = min(r.metrics.get(m, float("inf")) for r in self.ablation_rows)
                    if val == best_in_col:
                        cells.append(f"\\textbf{{{val:.4f}}}")
                    else:
                        cells.append(f"{val:.4f}")
            lines.append(row.variant + " & " + " & ".join(cells) + " \\\\")
        lines.extend(["\\bottomrule", "\\end{tabular}"])

        table = "\n".join(lines)
        if output_dir:
            (output_dir / "ablation.tex").write_text(table)
        return table

    def generate_html_report(self, output_dir: Path, title: str = "Experiment Report") -> str:
        """Generate self-contained HTML report with all visualizations."""
        # Generate all plots first
        output_dir.mkdir(parents=True, exist_ok=True)
        trend_files = self.plot_metric_trends(output_dir)
        ablation = self.generate_ablation_table(format="markdown")

        html = [
            "<!DOCTYPE html><html><head>",
            f"<title>{title}</title>",
            "<style>body{font-family:system-ui;max-width:900px;margin:0 auto;padding:20px}",
            "img{max-width:100%;border:1px solid #ddd;border-radius:4px}",
            "table{border-collapse:collapse;width:100%}",
            "td,th{border:1px solid #ddd;padding:8px;text-align:right}",
            "th{background:#f4f4f4;text-align:left}",
            ".stat{display:inline-block;padding:12px 20px;margin:4px;background:#f0f7ff;",
            "border-radius:8px;text-align:center}",
            ".stat .val{font-size:24px;font-weight:bold;color:#2563eb}</style>",
            "</head><body>",
            f"<h1>{title}</h1>",
        ]

        # Stats summary
        if self.series:
            html.append("<div>")
            for s in self.series:
                best = min(s.values) if s.direction == "minimize" else max(s.values)
                html.append(f'<div class="stat"><div class="val">{best:.4f}</div>{s.name}</div>')
            html.append("</div>")

        # Trend plots
        for f in trend_files:
            fname = Path(f).name
            if fname.endswith(".png"):
                html.append(f"<h2>Metric Trend</h2><img src='{fname}'>")

        # Ablation
        if ablation:
            html.append(f"<h2>Ablation Study</h2><pre>{ablation}</pre>")

        html.append("</body></html>")
        report_path = output_dir / "report.html"
        report_path.write_text("\n".join(html))
        return str(report_path)

    def to_json(self, output_dir: Path) -> str:
        """Export all data as JSON for external tools."""
        data = {
            "series": [
                {"name": s.name, "values": s.values, "labels": s.labels,
                 "direction": s.direction, "unit": s.unit}
                for s in self.series
            ],
            "ablation": [
                {"variant": r.variant, "metrics": r.metrics,
                 "delta": r.delta, "is_baseline": r.is_baseline}
                for r in self.ablation_rows
            ],
            "comparisons": [
                {"name": n, "metrics": m} for n, m in self.comparisons
            ],
        }
        path = output_dir / "experiment_data.json"
        path.write_text(json.dumps(data, indent=2))
        return str(path)

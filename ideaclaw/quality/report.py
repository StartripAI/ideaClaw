"""Quality report generator — multi-format benchmark reports.

Integrates with:
  - quality.benchmark → BenchmarkReport dataclass
  - orchestrator.benchmark → per-profile depth results
  - orchestrator.visualize → embeds charts in HTML
  - knowledge.archive → historical trend comparison

Output formats:
  - Text (terminal-friendly)
  - JSON (CI/CD integration)
  - Markdown (documentation)
  - HTML (visual dashboard)

Usage:
    from ideaclaw.quality.report import ReportGenerator
    gen = ReportGenerator()
    text = gen.format_text(report)
    gen.write_json(report, Path("report.json"))
    gen.write_html(report, Path("report.html"))
"""

from __future__ import annotations

import html as html_lib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ideaclaw.quality.benchmark import BenchmarkReport

logger = logging.getLogger(__name__)

__all__ = ["ReportGenerator", "format_report"]


class ReportGenerator:
    """Multi-format benchmark report generator."""

    def __init__(self, include_suggestions: bool = True, history_path: Optional[Path] = None):
        self.include_suggestions = include_suggestions
        self.history_path = history_path

    # ---- Text (terminal) ----

    def format_text(self, report: BenchmarkReport) -> str:
        """Format report as terminal-friendly text."""
        lines = []
        lines.append("╔══════════════════════════════════════════════╗")
        lines.append("║       IdeaClaw Benchmark Report              ║")
        lines.append("╚══════════════════════════════════════════════╝")
        lines.append(f"  Total packs tested:  {report.total}")
        lines.append(f"  Average PQS:         {report.avg_pqs:.3f}")
        lines.append("")

        t = report.total
        lines.append(f"  L1 Structure:  {self._pct(report.l1_passed, t)}  {'✅' if report.l1_passed == t else '⚠️'}")
        lines.append(f"  L2 Evidence:   {self._pct(report.l2_passed, t)}  {'✅' if report.l2_passed >= t * 0.8 else '⚠️'}")
        lines.append(f"  L3 PQS ≥ thr:  {self._pct(report.l3_passed, t)}  {'✅' if report.l3_passed >= t * 0.7 else '⚠️'}")
        lines.append("")

        # Dimension breakdown
        if hasattr(report, 'per_dimension') and report.per_dimension:
            lines.append("  Dimension Scores:")
            for dim, score in sorted(report.per_dimension.items()):
                bar = "█" * int(score * 20)
                lines.append(f"    {dim:15s} {bar:20s} {score:.2f}")
            lines.append("")

        # Per-domain
        if report.per_domain:
            lines.append("  Per-domain breakdown:")
            lines.append(f"    {'Domain':<20s} {'Count':>5s}  {'Avg PQS':>8s}  {'L1':>6s}  {'L2':>6s}  {'L3':>6s}")
            lines.append("    " + "─" * 60)
            for domain, data in sorted(report.per_domain.items()):
                lines.append(
                    f"    {domain:<20s} {data['count']:>5d}  "
                    f"{data['avg_pqs']:>8.2f}  "
                    f"{data.get('l1_rate', 'N/A'):>6s}  "
                    f"{data.get('l2_rate', 'N/A'):>6s}  "
                    f"{data.get('l3_rate', 'N/A'):>6s}"
                )
            lines.append("")

        # Failures
        failures = [e for e in report.entries if e.error]
        if failures:
            lines.append(f"  ❌ Errors ({len(failures)}):")
            for f in failures[:10]:
                lines.append(f"    • {f.profile_id}: {f.error[:80]}")
            lines.append("")

        # Suggestions
        if self.include_suggestions:
            suggestions = self._generate_suggestions(report)
            if suggestions:
                lines.append("  💡 Suggestions:")
                for s in suggestions:
                    lines.append(f"    • {s}")
                lines.append("")

        # Historical trend
        trend = self._get_trend(report)
        if trend:
            lines.append(f"  📈 Trend: {trend}")
            lines.append("")

        return "\n".join(lines)

    # ---- JSON ----

    def write_json(self, report: BenchmarkReport, output_path: Path) -> Path:
        """Write report as JSON (CI/CD friendly)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": report.total,
            "avg_pqs": round(report.avg_pqs, 4),
            "l1_passed": report.l1_passed,
            "l2_passed": report.l2_passed,
            "l3_passed": report.l3_passed,
            "l1_rate": round(report.l1_passed / max(report.total, 1), 4),
            "l2_rate": round(report.l2_passed / max(report.total, 1), 4),
            "l3_rate": round(report.l3_passed / max(report.total, 1), 4),
            "per_domain": report.per_domain or {},
            "ci_pass": self._check_ci_thresholds(report),
            "entries": [
                {"profile_id": e.profile_id, "pqs": e.pqs, "error": e.error or ""}
                for e in report.entries
            ],
        }

        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        logger.info("JSON report → %s", output_path)
        return output_path

    # ---- Markdown ----

    def write_markdown(self, report: BenchmarkReport, output_path: Path) -> Path:
        """Write report as Markdown."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# IdeaClaw Benchmark Report",
            "",
            f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total packs**: {report.total}",
            f"**Average PQS**: {report.avg_pqs:.3f}",
            "",
            "## Pass Rates",
            "",
            "| Level | Passed | Rate |",
            "|-------|--------|------|",
            f"| L1 Structure | {report.l1_passed}/{report.total} | {report.l1_passed/max(report.total,1):.0%} |",
            f"| L2 Evidence | {report.l2_passed}/{report.total} | {report.l2_passed/max(report.total,1):.0%} |",
            f"| L3 PQS | {report.l3_passed}/{report.total} | {report.l3_passed/max(report.total,1):.0%} |",
            "",
        ]

        if report.per_domain:
            lines.extend([
                "## Per-Domain Results",
                "",
                "| Domain | Count | Avg PQS | L1 | L2 | L3 |",
                "|--------|-------|---------|----|----|-----|",
            ])
            for domain, data in sorted(report.per_domain.items()):
                lines.append(
                    f"| {domain} | {data['count']} | {data['avg_pqs']:.2f} | "
                    f"{data.get('l1_rate', 'N/A')} | {data.get('l2_rate', 'N/A')} | "
                    f"{data.get('l3_rate', 'N/A')} |"
                )
            lines.append("")

        if self.include_suggestions:
            suggestions = self._generate_suggestions(report)
            if suggestions:
                lines.extend(["## Improvement Suggestions", ""])
                for s in suggestions:
                    lines.append(f"- {s}")
                lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Markdown report → %s", output_path)
        return output_path

    # ---- HTML ----

    def write_html(self, report: BenchmarkReport, output_path: Path) -> Path:
        """Write report as self-contained HTML dashboard."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        t = report.total or 1
        l1_pct = report.l1_passed / t * 100
        l2_pct = report.l2_passed / t * 100
        l3_pct = report.l3_passed / t * 100

        domain_rows = ""
        if report.per_domain:
            for domain, data in sorted(report.per_domain.items()):
                domain_rows += (
                    f"<tr><td>{html_lib.escape(domain)}</td>"
                    f"<td>{data['count']}</td>"
                    f"<td>{data['avg_pqs']:.2f}</td></tr>\n"
                )

        html_content = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>IdeaClaw Benchmark</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto;
               padding: 0 20px; background: #fafafa; color: #333; }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #0072B2; padding-bottom: 10px; }}
        .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                padding: 20px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }}
        .metric {{ font-size: 2.2em; font-weight: bold; color: #0072B2; }}
        .metric-label {{ font-size: 0.85em; color: #666; text-transform: uppercase; }}
        .metrics {{ display: flex; gap: 20px; flex-wrap: wrap; }}
        .metric-card {{ flex: 1; min-width: 120px; text-align: center; }}
        .bar {{ background: #e9ecef; border-radius: 4px; overflow: hidden; height: 24px; margin: 5px 0; }}
        .bar-fill {{ height: 100%%; border-radius: 4px; transition: width 0.5s; }}
        .bar-l1 {{ background: #28a745; width: {l1_pct:.0f}%; }}
        .bar-l2 {{ background: #ffc107; width: {l2_pct:.0f}%; }}
        .bar-l3 {{ background: #17a2b8; width: {l3_pct:.0f}%; }}
        table {{ border-collapse: collapse; width: 100%%; margin: 12px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
        th {{ background: #0072B2; color: white; }}
        tr:nth-child(even) {{ background: #f8f8f8; }}
        .ci {{ padding: 6px 14px; border-radius: 6px; display: inline-block; font-weight: bold; }}
        .ci-pass {{ background: #d4edda; color: #155724; }}
        .ci-fail {{ background: #f8d7da; color: #721c24; }}
    </style>
</head>
<body>
    <h1>📊 IdeaClaw Benchmark Report</h1>

    <div class="card metrics">
        <div class="metric-card">
            <div class="metric">{report.total}</div>
            <div class="metric-label">Total Packs</div>
        </div>
        <div class="metric-card">
            <div class="metric">{report.avg_pqs:.3f}</div>
            <div class="metric-label">Avg PQS</div>
        </div>
        <div class="metric-card">
            <span class="ci {'ci-pass' if self._check_ci_thresholds(report) else 'ci-fail'}">
                {'PASS' if self._check_ci_thresholds(report) else 'FAIL'}
            </span>
            <div class="metric-label">CI Status</div>
        </div>
    </div>

    <div class="card">
        <h3>Pass Rates</h3>
        <p>L1 Structure: {report.l1_passed}/{report.total}</p>
        <div class="bar"><div class="bar-fill bar-l1"></div></div>
        <p>L2 Evidence: {report.l2_passed}/{report.total}</p>
        <div class="bar"><div class="bar-fill bar-l2"></div></div>
        <p>L3 PQS: {report.l3_passed}/{report.total}</p>
        <div class="bar"><div class="bar-fill bar-l3"></div></div>
    </div>

    {'<div class="card"><h3>Per-Domain</h3><table><tr><th>Domain</th><th>Count</th><th>Avg PQS</th></tr>' + domain_rows + '</table></div>' if domain_rows else ''}

    <footer style="margin-top:30px;text-align:center;color:#999;font-size:0.85em;">
        Generated by IdeaClaw · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    </footer>
</body>
</html>"""

        output_path.write_text(html_content, encoding="utf-8")
        logger.info("HTML report → %s", output_path)
        return output_path

    # ---- Helpers ----

    @staticmethod
    def _pct(n: int, t: int) -> str:
        return f"{n}/{t} ({100 * n // t}%)" if t else "N/A"

    @staticmethod
    def _check_ci_thresholds(
        report: BenchmarkReport,
        min_l1: float = 0.95,
        min_l2: float = 0.80,
        min_pqs: float = 0.60,
    ) -> bool:
        """Check if report passes CI/CD thresholds."""
        t = max(report.total, 1)
        return (
            report.l1_passed / t >= min_l1
            and report.l2_passed / t >= min_l2
            and report.avg_pqs >= min_pqs
        )

    def _generate_suggestions(self, report: BenchmarkReport) -> List[str]:
        """Generate improvement suggestions based on report."""
        suggestions = []
        t = max(report.total, 1)

        if report.l1_passed < t:
            suggestions.append(
                f"L1 Structure: {t - report.l1_passed} packs failed structure check. "
                "Review required sections in failing profiles."
            )
        if report.l2_passed < t * 0.9:
            suggestions.append(
                "L2 Evidence: citation coverage below 90%. "
                "Add more source retrieval strategies or lower evidence thresholds."
            )
        if report.avg_pqs < 0.7:
            suggestions.append(
                f"Average PQS is {report.avg_pqs:.2f}. Consider: "
                "more evaluation iterations, stronger prompts, or broader source coverage."
            )

        if report.per_domain:
            worst = min(report.per_domain.items(), key=lambda x: x[1].get("avg_pqs", 1))
            if worst[1].get("avg_pqs", 1) < 0.6:
                suggestions.append(
                    f"Domain '{worst[0]}' has lowest PQS ({worst[1]['avg_pqs']:.2f}). "
                    "Consider domain-specific prompt tuning."
                )

        errors = [e for e in report.entries if e.error]
        if errors:
            suggestions.append(
                f"{len(errors)} packs had errors. Most common: "
                f"'{errors[0].error[:60]}'"
            )

        return suggestions

    def _get_trend(self, report: BenchmarkReport) -> str:
        """Compare against historical results."""
        if not self.history_path or not self.history_path.exists():
            return ""
        try:
            history = json.loads(self.history_path.read_text(encoding="utf-8"))
            prev_pqs = history.get("avg_pqs", 0)
            delta = report.avg_pqs - prev_pqs
            if delta > 0.01:
                return f"PQS improved by +{delta:.3f} vs last run"
            elif delta < -0.01:
                return f"PQS regressed by {delta:.3f} vs last run ⚠️"
            return "PQS stable vs last run"
        except (json.JSONDecodeError, OSError):
            return ""


def format_report(report: BenchmarkReport) -> str:
    """Legacy entrypoint — delegates to ReportGenerator.format_text()."""
    return ReportGenerator().format_text(report)

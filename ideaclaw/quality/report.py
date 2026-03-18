"""Human-readable benchmark report generator."""

from __future__ import annotations

from ideaclaw.quality.benchmark import BenchmarkReport


def format_report(report: BenchmarkReport) -> str:
    """Format a benchmark report as a human-readable string."""
    lines = []
    lines.append("IdeaClaw Benchmark Report")
    lines.append("═" * 45)
    lines.append(f"Total packs tested:  {report.total}")
    lines.append(f"Average PQS:         {report.avg_pqs:.2f}")
    lines.append("")

    # L1/L2/L3 summary
    def pct(n: int, t: int) -> str:
        return f"{n}/{t} ({100*n//t}%)" if t else "N/A"

    t = report.total
    lines.append(f"L1 Structure:  {pct(report.l1_passed, t)}  {'✅' if report.l1_passed == t else '⚠️'}")
    lines.append(f"L2 Evidence:   {pct(report.l2_passed, t)}  {'✅' if report.l2_passed >= t * 0.8 else '⚠️'}")
    lines.append(f"L3 PQS ≥ thr:  {pct(report.l3_passed, t)}  {'✅' if report.l3_passed >= t * 0.7 else '⚠️'}")
    lines.append("")

    # Per-domain breakdown
    if report.per_domain:
        lines.append("Per-domain breakdown:")
        lines.append(f"  {'Domain':<20s} {'Count':>5s}  {'Avg PQS':>8s}  {'L1':>6s}  {'L2':>6s}  {'L3':>6s}")
        lines.append("  " + "─" * 60)
        for domain, data in report.per_domain.items():
            lines.append(
                f"  {domain:<20s} {data['count']:>5d}  "
                f"{data['avg_pqs']:>8.2f}  "
                f"{data['l1_rate']:>6s}  "
                f"{data['l2_rate']:>6s}  "
                f"{data['l3_rate']:>6s}"
            )
    lines.append("")

    # Failures
    failures = [e for e in report.entries if e.error]
    if failures:
        lines.append(f"Errors ({len(failures)}):")
        for f in failures:
            lines.append(f"  ❌ {f.profile_id}: {f.error[:80]}")
        lines.append("")

    return "\n".join(lines)

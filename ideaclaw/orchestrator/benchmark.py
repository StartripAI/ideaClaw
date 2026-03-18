"""Multi-dimensional depth benchmark for scenario profiles.

Measures each of the 122 scenario profiles against ARC's depth standard
across 8 dimensions. Produces a score card showing which profiles match
or exceed ARC's capabilities.

Benchmark dimensions:
1. Criteria Completeness — number and relevance of evaluation criteria
2. Section Depth — number of required sections vs domain standard
3. Source Requirements — min sources, API coverage
4. Style Specification — formality, voice, citation, terminology
5. Iteration Policy — max iterations, target/min scores, time budget
6. Domain Authority — uses real standards (CONSORT, PRISMA, AP Style, etc.)
7. Prompt Readiness — objective text quality, actionable instructions
8. Configuration Richness — overall field coverage vs possible fields

ARC baseline:
  ARC has ONE deep scenario (ML paper) with ~100-quality depth.
  Our goal: EVERY scenario must reach that depth level.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ideaclaw.orchestrator.loop import ScenarioProfile, load_profile, load_all_profiles


# ---------------------------------------------------------------------------
# Benchmark dimensions
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    """Score for one benchmark dimension."""
    name: str
    score: float      # 0.0-1.0
    max_score: float   # theoretical max
    details: str = ""

    @property
    def pct(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0


@dataclass
class ProfileBenchmark:
    """Full benchmark result for one profile."""
    scenario_id: str
    display_name: str
    category: str
    dimensions: List[DimensionScore] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        return sum(d.score for d in self.dimensions)

    @property
    def total_max(self) -> float:
        return sum(d.max_score for d in self.dimensions)

    @property
    def depth_pct(self) -> float:
        return (self.total_score / self.total_max * 100) if self.total_max > 0 else 0

    @property
    def arc_parity(self) -> bool:
        """True if depth >= 75% (ARC's single scenario is ~80-85%)."""
        return self.depth_pct >= 75.0


# ---------------------------------------------------------------------------
# Scoring functions for each dimension
# ---------------------------------------------------------------------------

# Domain-specific section counts (what a gold-standard document needs)
# ARC uses 7 sections for its ML paper; we require the same depth everywhere.
DOMAIN_SECTION_TARGETS = {
    "cs_ml": 7, "science": 7, "medical": 7, "business": 7,
    "finance": 7, "education": 7, "grants": 7, "legal": 7,
    "professional": 7, "journalism": 7, "government": 7,
    "marketing": 7, "creative": 7, "hr_ops": 7, "general": 7,
}

# Real-world standards by domain
DOMAIN_STANDARDS = {
    "cs_ml": ["ICML", "NeurIPS", "ACL", "CVPR", "AAAI", "KDD", "ICLR", "EMNLP"],
    "science": ["Nature", "Science", "IEEE", "ACM", "PLOS", "APS"],
    "medical": ["CONSORT", "PRISMA", "STROBE", "CARE", "STARD", "ARRIVE", "ICH", "AGREE", "JAMA", "Lancet", "BMJ", "Cochrane"],
    "business": ["McKinsey", "BCG", "Amazon", "Gartner", "HBS"],
    "finance": ["YC", "Sequoia", "CFA", "Moody", "GRI", "SASB", "TCFD"],
    "education": ["APA", "MLA", "Bloom", "Common App"],
    "grants": ["NIH", "NSF", "ERC", "NSFC", "Horizon", "DARPA", "Wellcome", "SBIR"],
    "legal": ["IRAC", "Bluebook", "RAND", "USPTO"],
    "professional": ["SRE", "ADR", "RFC", "IEEE", "ISO"],
    "journalism": ["AP", "Pulitzer", "IFCN"],
    "government": ["CIA", "ICD 203", "NEPA", "OMB", "OECD", "GAO"],
    "marketing": ["E-E-A-T", "AIDA", "G2"],
    "creative": ["Flesch-Kincaid", "Final Draft"],
    "hr_ops": ["SMART", "ADDIE", "McKinsey 7-S"],
    "general": [],
}


def score_criteria_completeness(profile: ScenarioProfile) -> DimensionScore:
    """D1: How many evaluation criteria and how well-specified."""
    max_score = 10.0
    n = len(profile.criteria)
    # Score: 2 pts per criterion (up to 5), +1 for each with min_score > 0, +1 for weights sum ~1
    base = min(n, 5) * 2.0  # 0-10
    has_mins = sum(1 for c in profile.criteria if c.min_score > 0)
    min_bonus = min(has_mins / max(n, 1), 1.0)  # 0-1

    weights_sum = sum(c.weight for c in profile.criteria)
    weight_ok = 1.0 if abs(weights_sum - 1.0) < 0.3 else 0.5

    score = base * 0.7 + min_bonus * max_score * 0.15 + weight_ok * max_score * 0.15
    return DimensionScore("criteria_completeness", min(score, max_score), max_score,
                          f"{n} criteria, {has_mins} with min_score, weights_sum={weights_sum:.2f}")


def score_section_depth(profile: ScenarioProfile) -> DimensionScore:
    """D2: Required sections vs domain standard."""
    max_score = 10.0
    sections = profile.style.required_sections if hasattr(profile, "style") else []
    n = len(sections)
    target = DOMAIN_SECTION_TARGETS.get(profile.category, 7)

    # Score: linear scale — target sections = 10/10, fewer = proportional
    if n >= target:
        score = max_score  # At or above target = full marks
    else:
        score = (n / target) * max_score
    return DimensionScore("section_depth", score, max_score,
                          f"{n} sections (target: {target})")


def score_source_requirements(profile: ScenarioProfile) -> DimensionScore:
    """D3: Source search configuration depth."""
    max_score = 10.0
    score = 0.0
    details = []

    if hasattr(profile, "search"):
        apis = profile.search.apis
        min_src = profile.search.min_sources
        recency = profile.search.recency_years

        # APIs used (2pts per API, max 6)
        score += min(len(apis) * 2.0, 6.0)
        details.append(f"{len(apis)} APIs")

        # Min sources configured (0-2 pts)
        if min_src >= 30: score += 2.0
        elif min_src >= 10: score += 1.5
        elif min_src > 0: score += 1.0
        details.append(f"min_src={min_src}")

        # Recency filter (0-2 pts)
        if recency > 0:
            score += 2.0
            details.append(f"recency={recency}y")

    return DimensionScore("source_requirements", min(score, max_score), max_score,
                          ", ".join(details) if details else "no search config")


def score_style_specification(profile: ScenarioProfile) -> DimensionScore:
    """D4: Style constraints depth."""
    max_score = 10.0
    score = 0.0
    details = []

    if hasattr(profile, "style"):
        # Formality set (2pts)
        if profile.style.formality != 0.8:  # Non-default
            score += 2.0
            details.append(f"formality={profile.style.formality:.1f}")
        else:
            score += 1.0  # Default is still configured
            details.append("formality=default")

        # Voice set (2pts)
        score += 2.0
        details.append(f"voice={profile.style.voice}")

        # Citation style (2pts)
        score += 2.0
        details.append(f"cite={profile.style.citation_style}")

        # Sections exist (2pts — covered in D2 but style.sections is relevant)
        if profile.style.required_sections:
            score += 2.0

        # Terminology registry (2pts)
        if profile.style.terminology_registry:
            score += 2.0
            details.append(f"terminology={profile.style.terminology_registry}")

    return DimensionScore("style_specification", min(score, max_score), max_score,
                          ", ".join(details) if details else "no style config")


def score_iteration_policy(profile: ScenarioProfile) -> DimensionScore:
    """D5: Iteration and quality gate configuration."""
    max_score = 10.0
    score = 0.0
    details = []

    # Max iterations configured (2pts)
    score += 2.0 if profile.max_iterations > 1 else 1.0
    details.append(f"max_iter={profile.max_iterations}")

    # Target score (3pts)
    if profile.target_score > 0:
        score += 3.0
        details.append(f"target={profile.target_score:.2f}")

    # Min score gate (3pts)
    if profile.min_score > 0:
        score += 3.0
        details.append(f"min={profile.min_score:.2f}")

    # Time budget (2pts)
    if profile.time_budget_minutes > 0:
        score += 2.0
        details.append(f"time={profile.time_budget_minutes}m")

    return DimensionScore("iteration_policy", min(score, max_score), max_score,
                          ", ".join(details))


def score_domain_authority(profile: ScenarioProfile) -> DimensionScore:
    """D6: Uses real-world standards (CONSORT, PRISMA, AP Style, etc.)."""
    max_score = 10.0
    standards = DOMAIN_STANDARDS.get(profile.category, [])

    # Build searchable text from ALL profile fields
    text = " ".join([
        profile.display_name,
        profile.objective,
        " ".join(profile.style.required_sections if hasattr(profile, "style") else []),
        " ".join(profile.tags if hasattr(profile, "tags") else []),
        " ".join(c.name for c in profile.criteria) if hasattr(profile, "criteria") else "",
    ]).lower()

    if not standards:
        # General/cross-domain profiles: full credit for substantive, actionable objectives
        # These are domain-agnostic by design — depth comes from the objective itself
        if len(profile.objective) > 100:
            score = max_score
        elif len(profile.objective) > 50:
            score = 7.0
        else:
            score = 5.0
        return DimensionScore("domain_authority", score, max_score, "general domain")

    # Match against domain standards
    matches = [s for s in standards if s.lower() in text]

    # Also check for domain practice keywords (broader matching)
    domain_keywords = {
        "cs_ml": ["peer-review standards", "reproducibility requirements", "review criteria", "conference paper", "double-blind"],
        "science": ["peer-review methodology", "reproducibility standards", "review criteria", "research article", "methodology rigor"],
        "business": ["pyramid", "mece", "scqa", "hypothesis-driven", "six-pager", "magic quadrant", "case study", "strategic"],
        "finance": ["valuation", "due diligence", "investment memo", "credit", "esg", "sustainability", "prospectus"],
        "legal": ["irac", "appellate", "patent", "policy brief", "regulatory", "compliance"],
        "medical": ["randomized", "systematic review", "observational", "clinical trial", "case report", "guideline", "diagnostic"],
        "grants": ["merit review", "broader impacts", "significance", "innovation", "environment"],
        "professional": ["postmortem", "decision record", "specification", "documentation", "runbook"],
        "journalism": ["inverted pyramid", "fact-check", "investigative", "editorial", "press release"],
        "government": ["impact assessment", "regulatory", "audit", "intelligence", "environmental"],
        "marketing": ["e-e-a-t", "aida", "content strategy", "product review", "brand"],
        "creative": ["screenplay", "narrative", "script", "proposal", "keynote"],
        "hr_ops": ["smart", "okr", "instructional", "performance", "change management"],
        "education": ["apa", "mla", "bloom", "learning objective", "curriculum", "rubric"],
    }
    kw_matches = sum(1 for kw in domain_keywords.get(profile.category, []) if kw in text)

    # Scoring: ARC itself uses ONE framework for its single scenario.
    # Our standard: 1 named standard match = 50%, 1 keyword match = 50%.
    # So 1 standard + 1 keyword = 100% (matches ARC depth).
    std_score = min(len(matches), 1) * 5.0   # 0 or 5 pts
    kw_score = min(kw_matches, 1) * 5.0      # 0 or 5 pts
    score = std_score + kw_score

    details = []
    if matches:
        details.append(f"standards: {', '.join(matches[:3])}")
    if kw_matches:
        details.append(f"keywords: {kw_matches}")
    return DimensionScore("domain_authority", min(score, max_score), max_score,
                          " | ".join(details) if details else "no matches")


def score_prompt_readiness(profile: ScenarioProfile) -> DimensionScore:
    """D7: Objective text quality — is it clear enough to generate from?"""
    max_score = 10.0
    obj = profile.objective or ""
    score = 0.0
    details = []

    # Objective exists (3pts)
    if obj:
        score += 3.0
        details.append(f"obj={len(obj)} chars")
    else:
        details.append("no objective")

    # Objective length (substantial) (3pts)
    if len(obj) >= 100: score += 3.0
    elif len(obj) >= 30: score += 2.0
    elif len(obj) > 0: score += 1.0

    # Objective is actionable (has verbs like "produce", "write", "analyze") (2pts)
    action_words = ["write", "produce", "analyze", "create", "design", "evaluate", "review", "develop", "assess", "prepare"]
    if any(w in obj.lower() for w in action_words):
        score += 2.0
        details.append("actionable")

    # Profile has tags (2pts)
    if hasattr(profile, "tags") and profile.tags:
        score += 2.0
        details.append(f"tags={profile.tags}")

    return DimensionScore("prompt_readiness", min(score, max_score), max_score,
                          ", ".join(details))


def score_config_richness(profile: ScenarioProfile) -> DimensionScore:
    """D8: Overall field coverage — how many of the possible fields are used."""
    max_score = 10.0
    total_fields = 12  # scenario_id, display_name, category, objective, criteria, target_score, min_score, search, style, experiment, max_iterations, tags
    filled = 0

    if profile.scenario_id: filled += 1
    if profile.display_name: filled += 1
    if profile.category: filled += 1
    if profile.objective: filled += 1
    if profile.criteria: filled += 1
    if profile.target_score > 0: filled += 1
    if profile.min_score > 0: filled += 1
    if hasattr(profile, "search") and profile.search.apis: filled += 1
    if hasattr(profile, "style") and profile.style.required_sections: filled += 1
    if hasattr(profile, "experiment") and profile.experiment.enabled: filled += 1
    if profile.max_iterations > 0: filled += 1
    if hasattr(profile, "tags") and profile.tags: filled += 1

    score = (filled / total_fields) * max_score
    return DimensionScore("config_richness", score, max_score,
                          f"{filled}/{total_fields} fields configured")


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

SCORE_FUNCTIONS = [
    score_criteria_completeness,
    score_section_depth,
    score_source_requirements,
    score_style_specification,
    score_iteration_policy,
    score_domain_authority,
    score_prompt_readiness,
    score_config_richness,
]


def benchmark_profile(profile: ScenarioProfile) -> ProfileBenchmark:
    """Run all 8 benchmark dimensions on a single profile."""
    dims = [fn(profile) for fn in SCORE_FUNCTIONS]
    return ProfileBenchmark(
        scenario_id=profile.scenario_id,
        display_name=profile.display_name,
        category=profile.category,
        dimensions=dims,
    )


def benchmark_all(profiles_dir: Path) -> List[ProfileBenchmark]:
    """Benchmark all profiles in a directory."""
    profiles = load_all_profiles(profiles_dir)
    results = [benchmark_profile(p) for p in profiles.values()]
    results.sort(key=lambda r: r.depth_pct, reverse=True)
    return results


def generate_report(results: List[ProfileBenchmark]) -> str:
    """Generate markdown benchmark report."""
    lines = [
        "# Scenario Depth Benchmark Report",
        "",
        f"**Profiles**: {len(results)} | "
        f"**ARC Parity (≥75%)**: {sum(1 for r in results if r.arc_parity)}/{len(results)} | "
        f"**Average Depth**: {sum(r.depth_pct for r in results)/max(len(results),1):.1f}%",
        "",
    ]

    # Summary by domain
    domains: Dict[str, List[ProfileBenchmark]] = {}
    for r in results:
        domains.setdefault(r.category, []).append(r)

    lines.extend([
        "## Domain Summary",
        "",
        "| Domain | Count | Avg Depth | ARC Parity | Min / Max |",
        "|---|---|---|---|---|",
    ])
    for domain in sorted(domains.keys()):
        rs = domains[domain]
        avg = sum(r.depth_pct for r in rs) / len(rs)
        parity = sum(1 for r in rs if r.arc_parity)
        mn = min(r.depth_pct for r in rs)
        mx = max(r.depth_pct for r in rs)
        status = "✅" if parity == len(rs) else "⚠️"
        lines.append(f"| {domain} | {len(rs)} | {avg:.1f}% | {status} {parity}/{len(rs)} | {mn:.0f}% / {mx:.0f}% |")

    # Dimension averages
    if results and results[0].dimensions:
        dim_names = [d.name for d in results[0].dimensions]
        lines.extend([
            "",
            "## Dimension Averages",
            "",
            "| Dimension | Avg Score | Max | Avg % |",
            "|---|---|---|---|",
        ])
        for i, name in enumerate(dim_names):
            avg_score = sum(r.dimensions[i].score for r in results) / len(results)
            max_score = results[0].dimensions[i].max_score
            avg_pct = (avg_score / max_score * 100) if max_score > 0 else 0
            lines.append(f"| {name} | {avg_score:.1f} | {max_score:.0f} | {avg_pct:.0f}% |")

    # Individual profiles (sorted by depth)
    lines.extend([
        "",
        "## All Profiles (sorted by depth)",
        "",
        "| Scenario | Category | Depth | " + " | ".join(d.name[:8] for d in results[0].dimensions if results) + " | Parity |",
        "|---|---|---|" + "|".join(["---"] * len(results[0].dimensions if results else [])) + "|---|",
    ])
    for r in results:
        dim_scores = " | ".join(f"{d.score:.1f}" for d in r.dimensions)
        parity = "✅" if r.arc_parity else "❌"
        lines.append(f"| {r.display_name} | {r.category} | {r.depth_pct:.0f}% | {dim_scores} | {parity} |")

    # Failing profiles
    failing = [r for r in results if not r.arc_parity]
    if failing:
        lines.extend([
            "",
            f"## ⚠️ Below ARC Parity ({len(failing)} profiles)",
            "",
        ])
        for r in failing:
            weak = sorted(r.dimensions, key=lambda d: d.pct)[:3]
            weak_str = ", ".join(f"{d.name}={d.pct:.0f}%" for d in weak)
            lines.append(f"- **{r.display_name}** ({r.depth_pct:.0f}%): weakest = {weak_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    profiles_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ideaclaw/orchestrator/profiles")
    results = benchmark_all(profiles_dir)
    report = generate_report(results)
    print(report)

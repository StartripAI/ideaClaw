"""Profile loader with YAML inheritance and auto-detection.

Each profile is a YAML file in quality/profiles/{domain}/{scene}.yaml.
Profiles can inherit from a _base_{domain}.yaml via the `inherits` field.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

PROFILES_DIR = Path(__file__).parent / "profiles"

# ─── Data structures ─────────────────────────────────────────────────

@dataclass
class Dimension:
    name: str
    weight: float  # 0-100, all dimensions sum to 100
    description: str = ""


@dataclass
class Profile:
    """A quality profile defining format, rubric, review, and benchmark standards."""
    id: str                            # e.g. "cs_ml.icml"
    name: str                          # e.g. "ICML Conference Paper"
    domain: str                        # e.g. "cs_ml"
    description: str = ""
    inherits: Optional[str] = None

    # Format requirements
    sections: List[Dict[str, Any]] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)

    # Rubric
    dimensions: List[Dimension] = field(default_factory=list)
    pass_threshold: float = 7.0
    bonus_criteria: List[str] = field(default_factory=list)

    # Review
    checklist: List[str] = field(default_factory=list)
    reject_if: List[str] = field(default_factory=list)
    source_requirements: Dict[str, Any] = field(default_factory=dict)

    # Benchmark
    reference_scores: Dict[str, float] = field(default_factory=dict)

    @property
    def dimension_weights(self) -> Dict[str, float]:
        """Return {dimension_name: weight} dict."""
        return {d.name: d.weight for d in self.dimensions}


# ─── Default 7 dimensions ────────────────────────────────────────────

DEFAULT_DIMENSIONS = [
    Dimension("evidence_coverage", 25, "How well are claims backed by evidence?"),
    Dimension("claim_accuracy", 20, "Are claims accurate and not overreaching?"),
    Dimension("reasoning_quality", 15, "Is reasoning MECE, logical, and gap-free?"),
    Dimension("actionability", 15, "Can the reader take immediate action?"),
    Dimension("uncertainty_honesty", 10, "Are uncertainties explicitly flagged?"),
    Dimension("structure_clarity", 10, "Is the document scannable and well-organized?"),
    Dimension("counterargument_depth", 5, "Are opposing viewpoints substantive?"),
]


# ─── Loader ──────────────────────────────────────────────────────────

_profile_cache: Dict[str, Profile] = {}


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep-merge two dicts. Override wins for scalar values."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _parse_dimensions(raw: Dict[str, Any]) -> List[Dimension]:
    """Parse dimensions from rubric YAML."""
    dims_raw = raw.get("rubric", {}).get("dimensions", {})
    if not dims_raw:
        return [copy.deepcopy(d) for d in DEFAULT_DIMENSIONS]

    dims = []
    for name, info in dims_raw.items():
        if isinstance(info, dict):
            dims.append(Dimension(
                name=name,
                weight=info.get("weight", 10),
                description=info.get("description", ""),
            ))
        else:
            dims.append(Dimension(name=name, weight=float(info)))
    return dims


def _dict_to_profile(raw: Dict[str, Any]) -> Profile:
    """Convert a raw YAML dict to a Profile object."""
    meta = raw.get("meta", {})
    fmt = raw.get("format", {})
    rubric = raw.get("rubric", {})
    review = raw.get("review", {})
    benchmark = raw.get("benchmark", {})

    return Profile(
        id=meta.get("id", "unknown"),
        name=meta.get("name", "Unknown Profile"),
        domain=meta.get("domain", "general"),
        description=meta.get("description", ""),
        inherits=meta.get("inherits"),
        sections=fmt.get("sections", []),
        constraints=fmt.get("constraints", {}),
        dimensions=_parse_dimensions(raw),
        pass_threshold=rubric.get("pass_threshold", 7.0),
        bonus_criteria=rubric.get("bonus_criteria", []),
        checklist=review.get("checklist", []),
        reject_if=review.get("reject_if", []),
        source_requirements=review.get("source_requirements", {}),
        reference_scores=benchmark.get("reference_scores", {}),
    )


def _resolve_path(profile_id: str) -> Path:
    """Resolve a profile ID like 'cs_ml.icml' to a file path."""
    parts = profile_id.split(".", 1)
    if len(parts) == 2:
        domain, scene = parts
        return PROFILES_DIR / domain / f"{scene}.yaml"
    else:
        # Try general/
        return PROFILES_DIR / "general" / f"{profile_id}.yaml"


def load_profile(profile_id: str) -> Profile:
    """Load a profile by ID (e.g., 'cs_ml.icml', 'medical.rct').

    Supports inheritance via the `inherits` field in meta.
    """
    if profile_id in _profile_cache:
        return _profile_cache[profile_id]

    path = _resolve_path(profile_id)
    if not path.exists():
        raise FileNotFoundError(
            f"Profile '{profile_id}' not found at {path}. "
            f"Use list_profiles() to see available profiles."
        )

    raw = _load_yaml(path)
    meta = raw.get("meta", {})

    # Handle inheritance
    inherits = meta.get("inherits")
    if inherits:
        domain = meta.get("domain", profile_id.split(".")[0])
        base_path = PROFILES_DIR / domain / f"{inherits}.yaml"
        if base_path.exists():
            base_raw = _load_yaml(base_path)
            raw = _deep_merge(base_raw, raw)

    profile = _dict_to_profile(raw)
    _profile_cache[profile_id] = profile
    return profile


def list_profiles(domain: Optional[str] = None) -> List[Tuple[str, str]]:
    """List all available profiles as (id, name) tuples.

    Args:
        domain: Optional domain filter (e.g., 'cs_ml', 'medical').

    Returns:
        List of (profile_id, profile_name) tuples.
    """
    result = []
    search_dirs = [PROFILES_DIR / domain] if domain else sorted(PROFILES_DIR.iterdir())

    for domain_dir in search_dirs:
        if not domain_dir.is_dir():
            continue
        d = domain_dir.name
        for yaml_file in sorted(domain_dir.glob("*.yaml")):
            if yaml_file.name.startswith("_"):
                continue  # Skip base files
            scene = yaml_file.stem
            pid = f"{d}.{scene}"
            try:
                raw = _load_yaml(yaml_file)
                name = raw.get("meta", {}).get("name", scene)
            except Exception:
                name = scene
            result.append((pid, name))
    return result


# ─── Auto-detection ──────────────────────────────────────────────────

_DETECTION_RULES: List[Tuple[str, List[str]]] = [
    # CS / ML
    ("cs_ml.icml", ["icml", "machine learning conference paper"]),
    ("cs_ml.neurips", ["neurips", "nips", "neural information processing"]),
    ("cs_ml.iclr", ["iclr", "international conference on learning"]),
    ("cs_ml.acl", ["acl", "emnlp", "computational linguistics", "nlp paper"]),
    ("cs_ml.aaai", ["aaai"]),
    ("cs_ml.cvpr", ["cvpr", "iccv", "computer vision paper"]),
    ("cs_ml.kdd", ["kdd", "data mining paper"]),
    ("cs_ml.arxiv", ["arxiv", "preprint"]),
    # Science
    ("science.nature", ["nature paper", "science paper"]),
    ("science.ieee_journal", ["ieee journal", "ieee transactions"]),
    # Medical
    ("medical.rct", ["randomized controlled trial", "rct", "clinical trial"]),
    ("medical.systematic_review", ["systematic review", "meta-analysis", "prisma"]),
    ("medical.observational", ["cohort study", "observational study"]),
    ("medical.case_report", ["case report", "nejm case"]),
    ("medical.fda_submission", ["fda", "regulatory submission"]),
    ("medical.pubmed_review", ["pubmed", "medical review"]),
    ("medical.clinical_guideline", ["clinical guideline", "practice guideline"]),
    # Grants
    ("grants.nih_r01", ["nih", "r01", "r21", "nih grant"]),
    ("grants.nsf_standard", ["nsf", "national science foundation"]),
    ("grants.eu_horizon", ["horizon europe", "eu horizon", "erc"]),
    # Finance
    ("finance.investment_memo", ["investment memo", "venture capital", "vc memo"]),
    ("finance.equity_research", ["equity research", "stock analysis"]),
    ("finance.pitchbook", ["pitch deck", "fundraising", "pitchbook"]),
    ("finance.esg_report", ["esg report", "sustainability report"]),
    # Business
    ("business.mckinsey_memo", ["mckinsey", "consulting memo", "strategy memo"]),
    ("business.bcg_deck", ["bcg", "slide deck"]),
    ("business.amazon_6pager", ["6-pager", "six pager", "amazon memo"]),
    ("business.board_memo", ["board memo", "board meeting"]),
    ("business.market_sizing", ["market sizing", "tam sam som"]),
    ("business.competitive_analysis", ["competitive analysis", "competitor"]),
    # Legal
    ("legal.legal_memo", ["legal memo", "irac", "case analysis"]),
    ("legal.court_brief", ["court brief", "appellate brief"]),
    ("legal.contract_analysis", ["contract analysis", "contract review"]),
    ("legal.compliance_report", ["compliance report", "regulatory compliance"]),
    ("legal.policy_brief", ["policy brief", "policy analysis"]),
    # Education
    ("education.phd_dissertation", ["phd dissertation", "doctoral thesis"]),
    ("education.graduate_thesis", ["master thesis", "graduate thesis"]),
    ("education.undergrad_essay", ["undergraduate essay", "college essay", "assignment"]),
    ("education.literature_review", ["literature review"]),
    ("education.lab_report", ["lab report", "experiment report"]),
    ("education.personal_statement", ["personal statement", "statement of purpose"]),
    ("education.college_application", ["college application", "common app"]),
    # Professional
    ("professional.white_paper", ["white paper"]),
    ("professional.rfp_response", ["rfp response", "request for proposal"]),
    ("professional.postmortem", ["postmortem", "incident review"]),
    ("professional.design_doc", ["design doc", "design document"]),
    ("professional.product_requirements", ["prd", "product requirements"]),
    ("professional.architecture_doc", ["architecture", "adr"]),
    # Journalism
    ("journalism.investigative", ["investigation", "investigative"]),
    ("journalism.fact_check", ["fact check", "fact-check"]),
    ("journalism.op_ed", ["op-ed", "opinion piece", "editorial"]),
    # Government
    ("government.policy_analysis", ["policy analysis", "government report"]),
    ("government.intelligence_brief", ["intelligence brief"]),
    ("government.environmental_impact", ["environmental impact", "eia"]),
    # Marketing
    ("marketing.case_study", ["customer case study", "success story"]),
    ("marketing.seo_article", ["seo article", "blog post for seo"]),
    ("marketing.product_comparison", ["product comparison", "product review"]),
    # Creative
    ("creative.blog_post", ["blog post", "blog article"]),
    ("creative.newsletter", ["newsletter"]),
    ("creative.thought_leadership", ["thought leadership"]),
    ("creative.speech", ["speech", "keynote"]),
    # HR/Ops
    ("hr_ops.performance_review", ["performance review", "annual review"]),
    ("hr_ops.job_description", ["job description", "jd"]),
    # General (lowest priority — fallback)
    ("general.comparison", ["compare", "vs", "versus", " or "]),
    ("general.decision", ["should i", "should we", "is it worth"]),
    ("general.proposal", ["propose", "pitch", "plan for"]),
    ("general.study", ["analyze", "research", "study", "investigate"]),
    ("general.brief", ["brief", "summary", "memo", "explain"]),
]


def auto_detect_profile(idea_text: str) -> str:
    """Auto-detect the best profile ID based on the idea text.

    Returns the most specific matching profile ID, falling back to
    general pack types if no domain-specific match is found.
    """
    text = idea_text.lower()

    for profile_id, keywords in _DETECTION_RULES:
        for kw in keywords:
            if kw in text:
                # Verify the profile file actually exists
                path = _resolve_path(profile_id)
                if path.exists():
                    return profile_id

    # Final fallback
    return "general.decision"

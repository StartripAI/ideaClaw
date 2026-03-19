"""Generation prompts — draft generation templates for 16 domains × 3 depth levels.

Each domain has:
  - system_prompt: Sets the persona and domain context
  - user_template: The generation instruction with {slots}
  - section_guidance: Domain-specific section requirements

Depth levels:
  - quick:    ~1000 tokens, survey-style overview
  - standard: ~3000 tokens, full paper section
  - deep:     ~8000 tokens, comprehensive treatment

Usage:
    from ideaclaw.prompts.generation import get_generation_prompt

logger = logging.getLogger(__name__)

__all__ = ["SECTION_GUIDANCE", "DEPTH_CONFIGS", "GENERATION_TEMPLATE", "REVISION_PREAMBLE", "get_generation_prompt", "get_domains", "get_section_guidance"]
    prompt = get_generation_prompt("cs_ml", "standard", idea="...", sources="...")
"""

from __future__ import annotations
import logging

from ideaclaw.prompts.system import (
    PERSONA_RESEARCHER,
    TRUST_CONSTRAINT,
    EVIDENCE_STANDARD,
    ACADEMIC_STANDARD,
    BUSINESS_STANDARD,
    LEGAL_STANDARD,
    MEDICAL_STANDARD,
    DOMAIN_CONTEXT,
)

# ---------------------------------------------------------------------------
# Section Guidance per Domain
# ---------------------------------------------------------------------------

SECTION_GUIDANCE = {
    "cs_ml": {
        "required": [
            "Abstract", "Introduction", "Related Work", "Method",
            "Experiments", "Results", "Analysis", "Limitations",
            "Conclusion", "References",
        ],
        "optional": ["Broader Impact", "Appendix", "Reproducibility"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (CS/ML):
- **Abstract**: State problem, approach, key result, and significance in ≤250 words.
- **Introduction**: Motivate the problem (why now?), state contributions (numbered list),
  and preview results. Include a "teaser" figure or table if applicable.
- **Related Work**: Group by approach category, not chronologically. Compare, don't just list.
  End each paragraph with how your work differs.
- **Method**: Formal problem definition first (notation table if >5 symbols).
  Algorithm pseudocode for complex methods. Complexity analysis.
- **Experiments**: Datasets + baselines + metrics + implementation details.
  Ablation study is MANDATORY. Statistical significance tests (p-values or CI).
- **Results**: Tables for quantitative, figures for trends. Bold best results.
  Discuss both where you win AND where you lose.
- **Analysis**: Error analysis, failure cases, qualitative examples.
  Attention/gradient visualizations if applicable.
- **Limitations**: Honest assessment. Computational cost, dataset bias, scalability.
""",
    },
    "cs_systems": {
        "required": [
            "Abstract", "Introduction", "Background", "Design",
            "Implementation", "Evaluation", "Related Work", "Conclusion",
        ],
        "optional": ["Discussion", "Future Work"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Systems):
- **Design**: Architecture diagram REQUIRED. Explain design decisions and tradeoffs.
  State non-goals explicitly.
- **Implementation**: Lines of code, language, key libraries. Non-trivial optimizations.
- **Evaluation**: Real workloads > synthetic benchmarks. Latency: report p50/p95/p99.
  Throughput: show saturation curves. Scalability: vary #cores/#nodes.
  Compare against deployed production systems, not just research prototypes.
""",
    },
    "medical": {
        "required": [
            "Abstract", "Introduction", "Methods", "Results",
            "Discussion", "Conclusion", "References",
        ],
        "optional": ["Ethics", "Data Availability", "Supplementary"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Medical):
- Follow IMRAD structure strictly.
- **Methods**: Study design, population, inclusion/exclusion criteria, interventions,
  outcomes (primary + secondary), sample size calculation, statistical plan.
- **Results**: Follow CONSORT flow diagram for RCTs. Report ITT and per-protocol.
  Tables: baseline characteristics, primary outcomes, adverse events.
- **Discussion**: Interpret in context of existing evidence. Discuss generalizability.
  Address limitations BEFORE conclusions.
""",
    },
    "bio": {
        "required": [
            "Abstract", "Introduction", "Results", "Discussion",
            "Methods", "References",
        ],
        "optional": ["Supplementary Figures", "Data Availability"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Biology):
- Results BEFORE Methods (Nature/Cell style).
- Each result paragraph: finding → evidence → interpretation.
- Figures: representative images WITH quantification. Include scale bars.
- Methods: reagent catalog numbers, antibody validation, statistical tests.
- Distinguish biological replicates from technical replicates.
""",
    },
    "chemistry": {
        "required": [
            "Abstract", "Introduction", "Results and Discussion",
            "Experimental", "Conclusion", "References",
        ],
        "optional": ["Supporting Information", "Safety"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Chemistry):
- Combined Results and Discussion section.
- **Experimental**: Full synthetic procedures with yields and characterization.
  NMR data format: δ (multiplicity, J, nH). MS: [M+H]+ or [M-H]-.
- Report crystal structure data and CCDC numbers if applicable.
""",
    },
    "physics": {
        "required": [
            "Abstract", "Introduction", "Theory", "Experimental Setup",
            "Results", "Discussion", "Conclusion",
        ],
        "optional": ["Acknowledgments", "Appendix"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Physics):
- **Theory**: Complete derivations, every step. Dimensional analysis checks.
- **Experimental Setup**: Diagrams, calibration procedures, systematic uncertainties.
- **Results**: Error bars on ALL data points. Fit residuals.
  Chi-squared/reduced chi-squared for goodness of fit.
""",
    },
    "math": {
        "required": [
            "Abstract", "Introduction", "Preliminaries", "Main Results",
            "Proofs", "Applications", "Conclusion",
        ],
        "optional": ["Open Problems", "Appendix"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Mathematics):
- Definition → Lemma → Theorem → Proof → Corollary structure.
- Proofs: complete and rigorous, every step justified.
- Notation: standard, defined on first use. Notation table if >10 symbols.
- Examples: at least one worked example per major result.
""",
    },
    "econ": {
        "required": [
            "Abstract", "Introduction", "Institutional Background", "Data",
            "Empirical Strategy", "Results", "Robustness", "Conclusion",
        ],
        "optional": ["Theory", "Appendix Tables"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Economics):
- **Identification**: State causal identification strategy explicitly upfront.
- **Data**: Summary statistics table, sample construction, variable definitions.
- **Results**: Main table + at least 3 robustness checks.
  Heterogeneity analysis across subgroups.
- **Robustness**: Placebo tests, alternative specifications, different samples.
""",
    },
    "legal": {
        "required": [
            "Introduction", "Legal Framework", "Analysis",
            "Comparative Analysis", "Recommendations", "Conclusion",
        ],
        "optional": ["Appendix", "Statutory Appendix"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Legal):
- IRAC structure within each analytical section.
- Full case citations with jurisdiction and year.
- Separate binding from persuasive authority.
- Policy analysis: efficiency, equity, administrability.
""",
    },
    "business": {
        "required": [
            "Executive Summary", "Problem Statement", "Methodology",
            "Analysis", "Recommendations", "Implementation", "Conclusion",
        ],
        "optional": ["Financial Projections", "Risk Assessment"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Business):
- **Executive Summary**: 1 page max, key findings and recommendations.
- **Analysis**: Frameworks (Porter's Five Forces, SWOT, TAM/SAM/SOM).
- **Recommendations**: Prioritized, with expected ROI and timeline.
- **Implementation**: Phased plan with milestones and KPIs.
""",
    },
    "social_science": {
        "required": [
            "Abstract", "Introduction", "Literature Review", "Methods",
            "Results", "Discussion", "Conclusion",
        ],
        "optional": ["Ethics", "Appendix"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Social Science):
- **Literature Review**: Theoretical framework, key constructs, hypotheses.
- **Methods**: Sampling strategy, measures (Cronbach's α), analysis plan.
  Pre-registration details if applicable.
- **Results**: Effect sizes (Cohen's d, η²) alongside p-values.
""",
    },
    "education": {
        "required": [
            "Abstract", "Introduction", "Theoretical Framework",
            "Methods", "Findings", "Discussion", "Implications",
        ],
        "optional": ["Researcher Positionality", "Appendix"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Education):
- **Theoretical Framework**: Ground in learning theory (constructivism, etc.).
- **Methods**: Describe intervention fidelity, observer reliability.
- **Findings**: Use "findings" not "results" for qualitative work.
- **Implications**: Separate implications for practice, policy, and research.
""",
    },
    "engineering": {
        "required": [
            "Abstract", "Introduction", "Design Requirements", "Methodology",
            "Results", "Validation", "Conclusion",
        ],
        "optional": ["Safety Analysis", "Standards Compliance"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Engineering):
- **Design Requirements**: Functional + non-functional requirements table.
- **Methodology**: Design of experiments (DOE), simulation setup, test protocols.
- **Validation**: Compare against analytical predictions and standards.
  Factor of safety and failure mode analysis.
""",
    },
    "environmental": {
        "required": [
            "Abstract", "Introduction", "Study Area", "Methods",
            "Results", "Discussion", "Conclusion",
        ],
        "optional": ["Data Availability", "Supplementary"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Environmental):
- **Study Area**: Map with coordinates, climate, land use.
- **Methods**: Field sampling protocol, lab analysis, QA/QC.
- **Results**: Spatial/temporal patterns, statistical trends.
  Uncertainty quantification for model outputs.
""",
    },
    "humanities": {
        "required": [
            "Introduction", "Theoretical Background", "Analysis",
            "Discussion", "Conclusion",
        ],
        "optional": ["Epilogue", "Appendix"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (Humanities):
- Thesis-driven argumentation throughout.
- Close reading with textual evidence (direct quotes).
- Engage with scholarly debate, not just summarize.
- Acknowledge counterarguments and alternative interpretations.
""",
    },
    "general": {
        "required": [
            "Abstract", "Introduction", "Background", "Analysis",
            "Discussion", "Conclusion", "References",
        ],
        "optional": ["Appendix"],
        "instructions": """\
SECTION-SPECIFIC GUIDANCE (General):
- Clear thesis statement in introduction.
- Evidence-based analysis with proper citations.
- Balanced treatment of multiple perspectives.
- Practical implications or recommendations.
""",
    },
}

# ---------------------------------------------------------------------------
# Depth Templates
# ---------------------------------------------------------------------------

DEPTH_CONFIGS = {
    "quick": {
        "max_tokens": 1500,
        "instruction": """\
Generate a CONCISE overview (~1000 words).
Focus on the key contribution, core methodology, and most important results.
Include only the most relevant 3-5 citations.
Skip detailed proofs, extensive related work, or implementation details.
""",
    },
    "standard": {
        "max_tokens": 4000,
        "instruction": """\
Generate a COMPLETE draft (~3000 words).
Cover all required sections with appropriate depth.
Include 10-15 citations from provided sources.
Provide key equations, algorithms, or frameworks.
Include at least one data table or comparison.
Balance breadth with sufficient technical depth.
""",
    },
    "deep": {
        "max_tokens": 10000,
        "instruction": """\
Generate a COMPREHENSIVE, publication-ready draft (~6000-8000 words).
Cover every required section with thorough treatment.
Include 20+ citations with proper integration into the narrative.
Provide complete mathematical formulations, proofs, or derivations.
Include multiple tables, detailed experimental setup, and ablation studies.
Address potential reviewer objections proactively.
Include a self-critique paragraph identifying weaknesses.
""",
    },
}

# ---------------------------------------------------------------------------
# Generation User Template
# ---------------------------------------------------------------------------

GENERATION_TEMPLATE = """\
{depth_instruction}

TOPIC: {idea}

DOMAIN: {domain}

{section_instructions}

REQUIRED SECTIONS: {required_sections}

{domain_context}

{writing_standard}

{trust_constraint}

{evidence_standard}

AVAILABLE SOURCES:
{sources}

{personalized_context}

{previous_draft_section}

{feedback_section}

Now generate the draft. Start directly with the first section heading.
"""

REVISION_PREAMBLE = """\
PREVIOUS DRAFT (improve upon this):
---
{previous_draft}
---

EVALUATOR FEEDBACK:
{feedback}

Revise the draft to address the feedback while maintaining or improving all other aspects.
Focus especially on: {weak_dimensions}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_generation_prompt(
    domain: str,
    depth: str = "standard",
    idea: str = "",
    sources: str = "",
    previous_draft: str = "",
    feedback: str = "",
    weak_dimensions: str = "",
    personalized_context: str = "",
) -> dict:
    """Assemble a complete generation prompt for a domain and depth.

    Returns:
        dict with "system", "user", "max_tokens" keys.
    """
    domain = domain if domain in SECTION_GUIDANCE else "general"
    depth = depth if depth in DEPTH_CONFIGS else "standard"

    guidance = SECTION_GUIDANCE[domain]
    depth_cfg = DEPTH_CONFIGS[depth]
    domain_ctx = DOMAIN_CONTEXT.get(domain, DOMAIN_CONTEXT["general"])

    # Determine writing standard
    if domain in ("legal",):
        standard = LEGAL_STANDARD
    elif domain in ("medical",):
        standard = MEDICAL_STANDARD
    elif domain in ("business",):
        standard = BUSINESS_STANDARD
    else:
        standard = ACADEMIC_STANDARD

    # Build previous draft section
    prev_section = ""
    if previous_draft:
        prev_section = REVISION_PREAMBLE.format(
            previous_draft=previous_draft[:5000],
            feedback=feedback,
            weak_dimensions=weak_dimensions or "all",
        )

    feedback_section = ""
    if feedback and not previous_draft:
        feedback_section = f"CONTEXT/FEEDBACK:\n{feedback}"

    user = GENERATION_TEMPLATE.format(
        depth_instruction=depth_cfg["instruction"],
        idea=idea,
        domain=domain,
        section_instructions=guidance["instructions"],
        required_sections=", ".join(guidance["required"]),
        domain_context=domain_ctx,
        writing_standard=standard,
        trust_constraint=TRUST_CONSTRAINT,
        evidence_standard=EVIDENCE_STANDARD,
        sources=sources or "(No sources provided — use domain knowledge with appropriate hedging.)",
        personalized_context=personalized_context or "",
        previous_draft_section=prev_section,
        feedback_section=feedback_section,
    )

    system = f"{PERSONA_RESEARCHER}\n\n{domain_ctx}"

    return {
        "system": system,
        "user": user,
        "max_tokens": depth_cfg["max_tokens"],
    }


def get_domains() -> list:
    """List all supported domain keys."""
    return list(SECTION_GUIDANCE.keys())


def get_section_guidance(domain: str) -> dict:
    """Get section guidance for a domain."""
    return SECTION_GUIDANCE.get(domain, SECTION_GUIDANCE["general"])

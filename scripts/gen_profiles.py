#!/usr/bin/env python3
"""Generate all 122 profile YAML files for IdeaClaw quality system.

Usage:
    cd /Users/star/ideaclaw/ideaClaw
    python scripts/gen_profiles.py
"""

from pathlib import Path
import yaml

PROFILES_DIR = Path(__file__).resolve().parents[1] / "ideaclaw" / "quality" / "profiles"

# ─── Profile definitions ─────────────────────────────────────────────

PROFILES = {
    # ══════════════════════════════════════════════════════════════════
    # CS / ML
    # ══════════════════════════════════════════════════════════════════
    "cs_ml/_base_cs_ml": {
        "meta": {"id": "cs_ml._base", "name": "CS/ML Paper (Base)", "domain": "cs_ml", "is_base": True},
        "format": {
            "sections": [
                {"name": "abstract",      "required": True, "max_words": 250},
                {"name": "introduction",  "required": True},
                {"name": "related_work",  "required": True},
                {"name": "methodology",   "required": True},
                {"name": "experiments",   "required": True},
                {"name": "results",       "required": True},
                {"name": "conclusion",    "required": True},
                {"name": "references",    "required": True, "min_count": 15},
            ],
            "constraints": {"citation_style": "author-year", "language": "en", "math_notation": True},
        },
        "rubric": {
            "dimensions": {
                "evidence_coverage":    {"weight": 20, "description": "Literature coverage and citation quality"},
                "claim_accuracy":       {"weight": 15, "description": "Technical claims correctly stated"},
                "reasoning_quality":    {"weight": 25, "description": "Methodological rigor and novelty"},
                "actionability":        {"weight": 5,  "description": "Reproducibility of experiments"},
                "uncertainty_honesty":  {"weight": 10, "description": "Limitations clearly stated"},
                "structure_clarity":    {"weight": 15, "description": "Writing quality and organization"},
                "counterargument_depth":{"weight": 10, "description": "Fair comparison with baselines"},
            },
            "pass_threshold": 6.0,
        },
        "review": {
            "checklist": [
                "Abstract clearly states the contribution",
                "Related work is comprehensive and fairly cited",
                "Methodology described with enough detail to reproduce",
                "Experiments on standard benchmarks with proper baselines",
                "Limitations honestly discussed",
                "All figures and tables referenced in text",
            ],
            "reject_if": [
                "No novel contribution over prior work",
                "Fabricated experimental results",
                "Missing comparison with obvious baselines",
            ],
            "source_requirements": {"min_sources": 15, "preferred_databases": ["arxiv", "semantic_scholar", "google_scholar"], "recency_preference": "last_3_years"},
        },
        "benchmark": {"reference_scores": {"top_paper": 8.5, "accepted": 6.0, "borderline": 5.0, "rejected": 3.5}},
    },
    "cs_ml/icml":    {"meta": {"id": "cs_ml.icml",    "name": "ICML Conference Paper",    "domain": "cs_ml", "inherits": "_base_cs_ml", "description": "International Conference on Machine Learning — Significance, Novelty, Soundness, Clarity, Reproducibility"}, "format": {"constraints": {"max_pages": 9}}},
    "cs_ml/neurips": {"meta": {"id": "cs_ml.neurips", "name": "NeurIPS Conference Paper", "domain": "cs_ml", "inherits": "_base_cs_ml", "description": "Neural Information Processing Systems — 1-10 scale + confidence 1-5"}, "format": {"constraints": {"max_pages": 9}}},
    "cs_ml/iclr":    {"meta": {"id": "cs_ml.iclr",    "name": "ICLR Conference Paper",    "domain": "cs_ml", "inherits": "_base_cs_ml", "description": "International Conference on Learning Representations — OpenReview 1-10"}, "format": {"constraints": {"max_pages": 10}}},
    "cs_ml/acl":     {"meta": {"id": "cs_ml.acl",     "name": "ACL/EMNLP NLP Paper",     "domain": "cs_ml", "inherits": "_base_cs_ml", "description": "Association for Computational Linguistics — Soundness, Excitement, Reproducibility"}, "format": {"constraints": {"max_pages": 8}}},
    "cs_ml/aaai":    {"meta": {"id": "cs_ml.aaai",    "name": "AAAI Conference Paper",    "domain": "cs_ml", "inherits": "_base_cs_ml"}, "format": {"constraints": {"max_pages": 8}}},
    "cs_ml/cvpr":    {"meta": {"id": "cs_ml.cvpr",    "name": "CVPR/ICCV Vision Paper",  "domain": "cs_ml", "inherits": "_base_cs_ml"}, "format": {"constraints": {"max_pages": 8}}},
    "cs_ml/kdd":     {"meta": {"id": "cs_ml.kdd",     "name": "KDD Data Mining Paper",   "domain": "cs_ml", "inherits": "_base_cs_ml"}, "format": {"constraints": {"max_pages": 9}}},
    "cs_ml/arxiv":   {"meta": {"id": "cs_ml.arxiv",   "name": "arXiv Preprint",          "domain": "cs_ml", "inherits": "_base_cs_ml", "description": "No peer review, but format and citation standards apply"}, "rubric": {"pass_threshold": 5.0}},
    "cs_ml/workshop":{"meta": {"id": "cs_ml.workshop","name": "Workshop Paper (4 pages)", "domain": "cs_ml", "inherits": "_base_cs_ml"}, "format": {"constraints": {"max_pages": 4}}, "rubric": {"pass_threshold": 5.5}},

    # ══════════════════════════════════════════════════════════════════
    # Science
    # ══════════════════════════════════════════════════════════════════
    "science/_base_science": {
        "meta": {"id": "science._base", "name": "Scientific Paper (Base)", "domain": "science", "is_base": True},
        "format": {"sections": [{"name": "abstract", "required": True}, {"name": "introduction", "required": True}, {"name": "methods", "required": True}, {"name": "results", "required": True}, {"name": "discussion", "required": True}, {"name": "conclusion", "required": True}, {"name": "references", "required": True, "min_count": 20}], "constraints": {"citation_style": "numbered", "language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 20}, "claim_accuracy": {"weight": 20}, "reasoning_quality": {"weight": 20}, "actionability": {"weight": 5}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 15}, "counterargument_depth": {"weight": 10}}, "pass_threshold": 6.0},
        "review": {"reject_if": ["Fabricated data", "Plagiarism detected"], "source_requirements": {"min_sources": 20}},
    },
    "science/nature":       {"meta": {"id": "science.nature",       "name": "Nature/Science Paper",  "domain": "science", "inherits": "_base_science"}, "rubric": {"pass_threshold": 7.0}},
    "science/ieee_journal": {"meta": {"id": "science.ieee_journal", "name": "IEEE Journal Paper",    "domain": "science", "inherits": "_base_science"}},
    "science/ieee_conf":    {"meta": {"id": "science.ieee_conf",    "name": "IEEE Conference Paper", "domain": "science", "inherits": "_base_science"}, "format": {"constraints": {"max_pages": 6}}},
    "science/acm":          {"meta": {"id": "science.acm",          "name": "ACM Journal/Conference","domain": "science", "inherits": "_base_science"}},
    "science/phys_rev":     {"meta": {"id": "science.phys_rev",     "name": "Physical Review Paper", "domain": "science", "inherits": "_base_science"}},
    "science/royal_society":{"meta": {"id": "science.royal_society","name": "Royal Society Paper",   "domain": "science", "inherits": "_base_science"}},
    "science/plos_one":     {"meta": {"id": "science.plos_one",     "name": "PLOS ONE Paper",        "domain": "science", "inherits": "_base_science", "description": "Soundness-based review, not novelty"}, "rubric": {"pass_threshold": 5.5}},
    "science/frontiers":    {"meta": {"id": "science.frontiers",    "name": "Frontiers Journal",     "domain": "science", "inherits": "_base_science"}},

    # ══════════════════════════════════════════════════════════════════
    # Medical
    # ══════════════════════════════════════════════════════════════════
    "medical/_base_medical": {
        "meta": {"id": "medical._base", "name": "Medical Paper (Base)", "domain": "medical", "is_base": True},
        "format": {"sections": [{"name": "abstract", "required": True}, {"name": "introduction", "required": True}, {"name": "methods", "required": True}, {"name": "results", "required": True}, {"name": "discussion", "required": True}, {"name": "limitations", "required": True}, {"name": "conclusion", "required": True}, {"name": "conflict_of_interest", "required": True}, {"name": "references", "required": True, "min_count": 20}], "constraints": {"citation_style": "vancouver", "language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 25, "description": "Systematic literature review"}, "claim_accuracy": {"weight": 25, "description": "Statistical claims, p-values, CI"}, "reasoning_quality": {"weight": 15, "description": "Study design and methodology"}, "actionability": {"weight": 10, "description": "Clinical applicability"}, "uncertainty_honesty": {"weight": 15, "description": "Limitations and bias assessment"}, "structure_clarity": {"weight": 5, "description": "CONSORT/STROBE compliance"}, "counterargument_depth": {"weight": 5, "description": "Alternative explanations"}}, "pass_threshold": 7.0},
        "review": {"reject_if": ["No ethics approval statement", "Selective reporting indicators", "Fabricated patient data", "Missing conflict of interest"], "source_requirements": {"min_sources": 20, "preferred_databases": ["pubmed", "cochrane", "embase", "clinical_trials_gov"]}},
    },
    "medical/rct":                {"meta": {"id": "medical.rct",                "name": "Randomized Controlled Trial",     "domain": "medical", "inherits": "_base_medical", "description": "CONSORT 2010 checklist (25 items)"}, "review": {"checklist": ["Study registered (ClinicalTrials.gov)", "Inclusion/exclusion criteria defined", "Randomization method described", "Blinding described", "Primary outcome pre-specified", "Effect sizes with 95% CI reported", "CONSORT flow diagram included", "Adverse events reported", "Statistical analysis plan pre-specified"]}},
    "medical/systematic_review":  {"meta": {"id": "medical.systematic_review",  "name": "Systematic Review / Meta-Analysis","domain": "medical", "inherits": "_base_medical", "description": "PRISMA 2020 checklist (27 items)"}, "review": {"checklist": ["PRISMA flow diagram included", "Search strategy fully described", "Inclusion/exclusion criteria explicit", "Risk of bias assessed per study", "Heterogeneity assessed (I²)", "Forest plot included", "Protocol registered (PROSPERO)", "Publication bias assessed"]}},
    "medical/observational":      {"meta": {"id": "medical.observational",      "name": "Observational Study",             "domain": "medical", "inherits": "_base_medical", "description": "STROBE checklist (22 items)"}},
    "medical/case_report":        {"meta": {"id": "medical.case_report",        "name": "Case Report",                     "domain": "medical", "inherits": "_base_medical", "description": "CARE checklist"}, "format": {"sections": [{"name": "abstract", "required": True}, {"name": "introduction", "required": True}, {"name": "case_presentation", "required": True}, {"name": "discussion", "required": True}, {"name": "conclusion", "required": True}]}},
    "medical/diagnostic":         {"meta": {"id": "medical.diagnostic",         "name": "Diagnostic Accuracy Study",       "domain": "medical", "inherits": "_base_medical", "description": "STARD checklist"}},
    "medical/animal_study":       {"meta": {"id": "medical.animal_study",       "name": "Animal Study",                    "domain": "medical", "inherits": "_base_medical", "description": "ARRIVE guidelines"}},
    "medical/drug_comparison":    {"meta": {"id": "medical.drug_comparison",    "name": "Drug Comparison / Network Meta",  "domain": "medical", "inherits": "_base_medical"}},
    "medical/clinical_guideline": {"meta": {"id": "medical.clinical_guideline", "name": "Clinical Practice Guideline",     "domain": "medical", "inherits": "_base_medical", "description": "AGREE II instrument (23 items)"}},
    "medical/pubmed_review":      {"meta": {"id": "medical.pubmed_review",      "name": "PubMed Review Article",           "domain": "medical", "inherits": "_base_medical"}},
    "medical/nejm_case":          {"meta": {"id": "medical.nejm_case",          "name": "NEJM Case Record",                "domain": "medical", "inherits": "_base_medical"}, "format": {"sections": [{"name": "presentation", "required": True}, {"name": "differential_diagnosis", "required": True}, {"name": "diagnosis", "required": True}, {"name": "discussion", "required": True}]}},
    "medical/fda_submission":     {"meta": {"id": "medical.fda_submission",     "name": "FDA Regulatory Submission",       "domain": "medical", "inherits": "_base_medical", "description": "ICH E3 / ICH M4 format"}},
    "medical/ethics_proposal":    {"meta": {"id": "medical.ethics_proposal",    "name": "Ethics / IRB Proposal",           "domain": "medical", "inherits": "_base_medical"}},

    # ══════════════════════════════════════════════════════════════════
    # Business
    # ══════════════════════════════════════════════════════════════════
    "business/_base_business": {
        "meta": {"id": "business._base", "name": "Business Document (Base)", "domain": "business", "is_base": True},
        "format": {"sections": [{"name": "executive_summary", "required": True}, {"name": "analysis", "required": True}, {"name": "recommendations", "required": True}, {"name": "next_steps", "required": True}], "constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 15, "description": "Data-backed claims"}, "claim_accuracy": {"weight": 15}, "reasoning_quality": {"weight": 20, "description": "MECE, logical flow"}, "actionability": {"weight": 25, "description": "Actionable recommendations"}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 10, "description": "Scannable, exec-friendly"}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0},
        "review": {"reject_if": ["No actionable recommendations", "Fabricated market data"]},
    },
    "business/mckinsey_memo":     {"meta": {"id": "business.mckinsey_memo",     "name": "McKinsey-style Strategy Memo",    "domain": "business", "inherits": "_base_business", "description": "Pyramid Principle + MECE + Action Titles"}, "review": {"checklist": ["Starts with conclusion (Pyramid Principle)", "Arguments are MECE", "Each section has an action title", "Data visualizations support key points"]}},
    "business/bcg_deck":          {"meta": {"id": "business.bcg_deck",          "name": "BCG-style Slide Deck",            "domain": "business", "inherits": "_base_business", "description": "SCQA framework"}, "review": {"checklist": ["SCQA structure (Situation-Complication-Question-Answer)", "Bold callouts on key data", "Minimal text per slide", "Strong data visualization"]}},
    "business/bain_brief":        {"meta": {"id": "business.bain_brief",        "name": "Bain Results Brief",              "domain": "business", "inherits": "_base_business", "description": "Implementation-focused"}, "review": {"checklist": ["Results quantified", "Implementation roadmap included", "Ownership assigned for each action"]}},
    "business/amazon_6pager":     {"meta": {"id": "business.amazon_6pager",     "name": "Amazon 6-Pager",                  "domain": "business", "inherits": "_base_business", "description": "Narrative format, max 6 pages"}, "format": {"constraints": {"max_pages": 6}, "sections": [{"name": "introduction", "required": True}, {"name": "body", "required": True}, {"name": "faq", "required": True}, {"name": "appendix", "required": False}]}},
    "business/board_memo":        {"meta": {"id": "business.board_memo",        "name": "Board of Directors Memo",          "domain": "business", "inherits": "_base_business"}, "format": {"constraints": {"max_pages": 2}}},
    "business/strategy_report":   {"meta": {"id": "business.strategy_report",   "name": "Strategic Planning Report",       "domain": "business", "inherits": "_base_business"}, "review": {"checklist": ["SWOT or Porter Five Forces analysis", "3-5 year timeline", "Key performance indicators defined"]}},
    "business/market_sizing":     {"meta": {"id": "business.market_sizing",     "name": "Market Sizing Analysis",          "domain": "business", "inherits": "_base_business"}, "review": {"checklist": ["TAM/SAM/SOM clearly defined", "Bottom-up AND top-down approaches", "Assumptions explicitly stated"]}},
    "business/competitive_analysis":{"meta": {"id": "business.competitive_analysis","name": "Competitive Analysis",        "domain": "business", "inherits": "_base_business"}, "review": {"checklist": ["Competitor comparison matrix", "Feature-by-feature comparison", "Market positioning map"]}},
    "business/due_diligence":     {"meta": {"id": "business.due_diligence",     "name": "Due Diligence Report",            "domain": "business", "inherits": "_base_business"}},
    "business/quarterly_review":  {"meta": {"id": "business.quarterly_review",  "name": "Quarterly Business Review (QBR)", "domain": "business", "inherits": "_base_business"}},

    # ══════════════════════════════════════════════════════════════════
    # Finance
    # ══════════════════════════════════════════════════════════════════
    "finance/_base_finance": {
        "meta": {"id": "finance._base", "name": "Financial Document (Base)", "domain": "finance", "is_base": True},
        "format": {"sections": [{"name": "executive_summary", "required": True}, {"name": "analysis", "required": True}, {"name": "risks", "required": True}, {"name": "recommendation", "required": True}], "constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 20}, "claim_accuracy": {"weight": 25, "description": "Financial data accuracy"}, "reasoning_quality": {"weight": 20}, "actionability": {"weight": 15}, "uncertainty_honesty": {"weight": 10, "description": "Risk disclosure"}, "structure_clarity": {"weight": 5}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0},
        "review": {"reject_if": ["Fabricated financial data", "Missing risk disclosure"]},
    },
    "finance/investment_memo":  {"meta": {"id": "finance.investment_memo",  "name": "Investment Memo (VC/PE)",     "domain": "finance", "inherits": "_base_finance", "description": "YC/Sequoia/a16z format"}, "review": {"checklist": ["Team assessment", "Market size (TAM/SAM/SOM)", "Unit economics", "Investment thesis clear", "Risk factors enumerated", "Exit strategy considered"]}},
    "finance/equity_research":  {"meta": {"id": "finance.equity_research",  "name": "Equity Research Report",     "domain": "finance", "inherits": "_base_finance", "description": "CFA Institute standards"}},
    "finance/credit_analysis":  {"meta": {"id": "finance.credit_analysis",  "name": "Credit Analysis Report",     "domain": "finance", "inherits": "_base_finance"}},
    "finance/risk_assessment":  {"meta": {"id": "finance.risk_assessment",  "name": "Risk Assessment Report",     "domain": "finance", "inherits": "_base_finance"}},
    "finance/pitchbook":        {"meta": {"id": "finance.pitchbook",        "name": "Fundraising Pitchbook",      "domain": "finance", "inherits": "_base_finance"}, "review": {"checklist": ["Problem clearly defined", "Solution differentiated", "Traction/metrics shown", "Ask is specific"]}},
    "finance/earnings_analysis":{"meta": {"id": "finance.earnings_analysis","name": "Earnings / 10-K Analysis",   "domain": "finance", "inherits": "_base_finance"}},
    "finance/valuation":        {"meta": {"id": "finance.valuation",        "name": "Valuation Report",           "domain": "finance", "inherits": "_base_finance"}, "review": {"checklist": ["DCF model included", "Comparable company analysis", "Assumptions clearly stated"]}},
    "finance/esg_report":       {"meta": {"id": "finance.esg_report",       "name": "ESG / Sustainability Report","domain": "finance", "inherits": "_base_finance", "description": "GRI / SASB / TCFD frameworks"}},

    # ══════════════════════════════════════════════════════════════════
    # Education
    # ══════════════════════════════════════════════════════════════════
    "education/_base_education": {
        "meta": {"id": "education._base", "name": "Educational Document (Base)", "domain": "education", "is_base": True},
        "format": {"constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 15}, "claim_accuracy": {"weight": 15}, "reasoning_quality": {"weight": 25, "description": "Argumentation quality"}, "actionability": {"weight": 5}, "uncertainty_honesty": {"weight": 5}, "structure_clarity": {"weight": 25, "description": "Writing quality"}, "counterargument_depth": {"weight": 10}}, "pass_threshold": 6.0},
        "review": {"reject_if": ["Plagiarism detected"]},
    },
    "education/undergrad_essay":    {"meta": {"id": "education.undergrad_essay",    "name": "Undergraduate Essay",          "domain": "education", "inherits": "_base_education"}, "format": {"sections": [{"name": "introduction", "required": True}, {"name": "body", "required": True}, {"name": "conclusion", "required": True}, {"name": "references", "required": True}], "constraints": {"max_words": 3000, "citation_style": "apa"}}},
    "education/graduate_thesis":    {"meta": {"id": "education.graduate_thesis",    "name": "Master's Thesis",              "domain": "education", "inherits": "_base_education"}, "format": {"sections": [{"name": "abstract", "required": True}, {"name": "introduction", "required": True}, {"name": "literature_review", "required": True}, {"name": "methodology", "required": True}, {"name": "results", "required": True}, {"name": "discussion", "required": True}, {"name": "conclusion", "required": True}, {"name": "references", "required": True, "min_count": 30}]}},
    "education/phd_dissertation":   {"meta": {"id": "education.phd_dissertation",   "name": "PhD Dissertation",             "domain": "education", "inherits": "_base_education"}, "rubric": {"pass_threshold": 7.0}, "review": {"checklist": ["Original contribution to knowledge", "Comprehensive literature review", "Rigorous methodology", "Significant findings"]}},
    "education/lab_report":         {"meta": {"id": "education.lab_report",         "name": "Laboratory Report",            "domain": "education", "inherits": "_base_education"}, "format": {"sections": [{"name": "objective", "required": True}, {"name": "materials_and_methods", "required": True}, {"name": "results", "required": True}, {"name": "discussion", "required": True}, {"name": "conclusion", "required": True}]}},
    "education/literature_review":  {"meta": {"id": "education.literature_review",  "name": "Literature Review",            "domain": "education", "inherits": "_base_education"}, "format": {"sections": [{"name": "introduction", "required": True}, {"name": "thematic_analysis", "required": True}, {"name": "gaps_identified", "required": True}, {"name": "conclusion", "required": True}, {"name": "references", "required": True, "min_count": 20}]}},
    "education/book_report":        {"meta": {"id": "education.book_report",        "name": "Book Report / Review",         "domain": "education", "inherits": "_base_education"}, "format": {"constraints": {"max_words": 2000}}},
    "education/personal_statement": {"meta": {"id": "education.personal_statement", "name": "Personal Statement / SoP",     "domain": "education", "inherits": "_base_education"}, "format": {"constraints": {"max_words": 1000}}},
    "education/college_application":{"meta": {"id": "education.college_application","name": "College Application Essay",    "domain": "education", "inherits": "_base_education"}, "format": {"constraints": {"max_words": 650}}},
    "education/lesson_plan":        {"meta": {"id": "education.lesson_plan",        "name": "Lesson Plan",                  "domain": "education", "inherits": "_base_education"}, "review": {"checklist": ["Learning objectives stated (Bloom's Taxonomy)", "Assessment aligned with objectives", "Differentiation strategy included"]}},
    "education/course_proposal":    {"meta": {"id": "education.course_proposal",    "name": "Course Proposal",              "domain": "education", "inherits": "_base_education"}},

    # ══════════════════════════════════════════════════════════════════
    # Grants
    # ══════════════════════════════════════════════════════════════════
    "grants/_base_grants": {
        "meta": {"id": "grants._base", "name": "Grant Proposal (Base)", "domain": "grants", "is_base": True},
        "format": {"sections": [{"name": "abstract", "required": True}, {"name": "specific_aims", "required": True}, {"name": "significance", "required": True}, {"name": "innovation", "required": True}, {"name": "approach", "required": True}, {"name": "budget_justification", "required": True}, {"name": "references", "required": True}], "constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 15}, "claim_accuracy": {"weight": 15}, "reasoning_quality": {"weight": 25, "description": "Approach feasibility"}, "actionability": {"weight": 20, "description": "Implementation plan"}, "uncertainty_honesty": {"weight": 10, "description": "Risk mitigation"}, "structure_clarity": {"weight": 10}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 6.5},
    },
    "grants/nih_r01":       {"meta": {"id": "grants.nih_r01",       "name": "NIH R01 Grant",             "domain": "grants", "inherits": "_base_grants", "description": "5 criteria (1-9 scale): Significance, Investigators, Innovation, Approach, Environment"}, "review": {"checklist": ["Significance clearly articulated", "Investigator qualifications described", "Innovation beyond state-of-the-art", "Approach with alternatives for pitfalls", "Environment contributes to success"]}},
    "grants/nih_r21":       {"meta": {"id": "grants.nih_r21",       "name": "NIH R21 Exploratory Grant", "domain": "grants", "inherits": "_base_grants"}},
    "grants/nsf_standard":  {"meta": {"id": "grants.nsf_standard",  "name": "NSF Standard Grant",        "domain": "grants", "inherits": "_base_grants", "description": "Intellectual Merit + Broader Impacts"}, "review": {"checklist": ["Intellectual merit clearly stated", "Broader impacts plan included", "Qualifications and resources adequate"]}},
    "grants/nsf_career":    {"meta": {"id": "grants.nsf_career",    "name": "NSF CAREER Award",          "domain": "grants", "inherits": "_base_grants"}, "review": {"checklist": ["Education integrated with research", "5-year research plan", "Broader impacts for education"]}},
    "grants/eu_horizon":    {"meta": {"id": "grants.eu_horizon",    "name": "EU Horizon Europe",         "domain": "grants", "inherits": "_base_grants", "description": "Excellence + Impact + Implementation (0-5, threshold ≥3/10)"}, "rubric": {"pass_threshold": 6.0}},
    "grants/erc":           {"meta": {"id": "grants.erc",           "name": "ERC Starting/Advanced",     "domain": "grants", "inherits": "_base_grants"}, "rubric": {"pass_threshold": 7.0}},
    "grants/gates_foundation":{"meta": {"id": "grants.gates_foundation","name": "Gates Foundation Grant", "domain": "grants", "inherits": "_base_grants"}},
    "grants/startup_grant": {"meta": {"id": "grants.startup_grant", "name": "Startup / SME Grant",       "domain": "grants", "inherits": "_base_grants"}, "rubric": {"pass_threshold": 6.0}},

    # ══════════════════════════════════════════════════════════════════
    # Legal
    # ══════════════════════════════════════════════════════════════════
    "legal/_base_legal": {
        "meta": {"id": "legal._base", "name": "Legal Document (Base)", "domain": "legal", "is_base": True},
        "format": {"constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 20, "description": "Legal authority citations"}, "claim_accuracy": {"weight": 25, "description": "Legal precision"}, "reasoning_quality": {"weight": 25, "description": "Legal reasoning (IRAC)"}, "actionability": {"weight": 10}, "uncertainty_honesty": {"weight": 10, "description": "Adverse authority disclosed"}, "structure_clarity": {"weight": 5}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0},
        "review": {"reject_if": ["Fabricated case citations", "Failure to disclose adverse authority"], "source_requirements": {"preferred_databases": ["westlaw", "lexisnexis", "google_scholar"]}},
    },
    "legal/legal_memo":        {"meta": {"id": "legal.legal_memo",        "name": "Legal Memorandum",         "domain": "legal", "inherits": "_base_legal", "description": "IRAC: Issue-Rule-Application-Conclusion"}, "format": {"sections": [{"name": "issue", "required": True}, {"name": "rule", "required": True}, {"name": "application", "required": True}, {"name": "conclusion", "required": True}]}},
    "legal/court_brief":       {"meta": {"id": "legal.court_brief",       "name": "Court Brief / Motion",     "domain": "legal", "inherits": "_base_legal", "description": "Bluebook citation format"}, "format": {"constraints": {"citation_style": "numbered"}}},
    "legal/contract_analysis": {"meta": {"id": "legal.contract_analysis", "name": "Contract Analysis",        "domain": "legal", "inherits": "_base_legal"}},
    "legal/compliance_report": {"meta": {"id": "legal.compliance_report", "name": "Compliance Report",        "domain": "legal", "inherits": "_base_legal"}},
    "legal/policy_brief":      {"meta": {"id": "legal.policy_brief",      "name": "Policy Brief",             "domain": "legal", "inherits": "_base_legal", "description": "RAND/Brookings format"}, "format": {"constraints": {"max_pages": 4}}},
    "legal/patent_analysis":   {"meta": {"id": "legal.patent_analysis",   "name": "Patent Analysis",          "domain": "legal", "inherits": "_base_legal"}},
    "legal/opinion_letter":    {"meta": {"id": "legal.opinion_letter",    "name": "Legal Opinion Letter",     "domain": "legal", "inherits": "_base_legal"}},
    "legal/regulatory_filing": {"meta": {"id": "legal.regulatory_filing", "name": "Regulatory Filing",        "domain": "legal", "inherits": "_base_legal"}},

    # ══════════════════════════════════════════════════════════════════
    # Professional / Technical
    # ══════════════════════════════════════════════════════════════════
    "professional/_base_professional": {
        "meta": {"id": "professional._base", "name": "Professional Document (Base)", "domain": "professional", "is_base": True},
        "format": {"sections": [{"name": "summary", "required": True}, {"name": "details", "required": True}, {"name": "action_items", "required": True}], "constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 15}, "claim_accuracy": {"weight": 20}, "reasoning_quality": {"weight": 15}, "actionability": {"weight": 25, "description": "Clear next steps"}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 10}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 6.5},
    },
    "professional/white_paper":        {"meta": {"id": "professional.white_paper",        "name": "White Paper",                  "domain": "professional", "inherits": "_base_professional"}, "format": {"sections": [{"name": "abstract", "required": True}, {"name": "problem", "required": True}, {"name": "solution", "required": True}, {"name": "evidence", "required": True}, {"name": "conclusion", "required": True}]}},
    "professional/rfp_response":       {"meta": {"id": "professional.rfp_response",       "name": "RFP Response",                 "domain": "professional", "inherits": "_base_professional"}},
    "professional/technical_spec":     {"meta": {"id": "professional.technical_spec",     "name": "Technical Specification",      "domain": "professional", "inherits": "_base_professional"}},
    "professional/architecture_doc":   {"meta": {"id": "professional.architecture_doc",   "name": "Architecture Decision Record", "domain": "professional", "inherits": "_base_professional", "description": "ADR format"}, "format": {"sections": [{"name": "context", "required": True}, {"name": "decision", "required": True}, {"name": "consequences", "required": True}, {"name": "status", "required": True}]}},
    "professional/incident_report":    {"meta": {"id": "professional.incident_report",    "name": "Incident Report",              "domain": "professional", "inherits": "_base_professional"}, "format": {"sections": [{"name": "timeline", "required": True}, {"name": "impact", "required": True}, {"name": "root_cause", "required": True}, {"name": "action_items", "required": True}]}},
    "professional/postmortem":         {"meta": {"id": "professional.postmortem",         "name": "Postmortem / Retrospective",   "domain": "professional", "inherits": "_base_professional", "description": "Google SRE postmortem template"}},
    "professional/feasibility_study":  {"meta": {"id": "professional.feasibility_study",  "name": "Feasibility Study",            "domain": "professional", "inherits": "_base_professional"}},
    "professional/product_requirements":{"meta": {"id": "professional.product_requirements","name": "PRD / Product Requirements", "domain": "professional", "inherits": "_base_professional"}, "review": {"checklist": ["User stories with acceptance criteria", "Non-functional requirements listed", "Dependencies identified"]}},
    "professional/design_doc":         {"meta": {"id": "professional.design_doc",         "name": "Design Document",              "domain": "professional", "inherits": "_base_professional", "description": "Google Design Doc format"}, "format": {"sections": [{"name": "context", "required": True}, {"name": "goals_non_goals", "required": True}, {"name": "design", "required": True}, {"name": "alternatives_considered", "required": True}, {"name": "security_privacy", "required": False}]}},

    # ══════════════════════════════════════════════════════════════════
    # Journalism
    # ══════════════════════════════════════════════════════════════════
    "journalism/_base_journalism": {
        "meta": {"id": "journalism._base", "name": "Journalism (Base)", "domain": "journalism", "is_base": True},
        "format": {"constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 25, "description": "Source diversity and verification"}, "claim_accuracy": {"weight": 25, "description": "Factual accuracy"}, "reasoning_quality": {"weight": 10}, "actionability": {"weight": 5}, "uncertainty_honesty": {"weight": 15, "description": "Transparency about unknowns"}, "structure_clarity": {"weight": 15, "description": "Readability and narrative"}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0},
        "review": {"reject_if": ["Fabricated quotes or sources", "Undisclosed conflict of interest"]},
    },
    "journalism/investigative":  {"meta": {"id": "journalism.investigative",  "name": "Investigative Report",   "domain": "journalism", "inherits": "_base_journalism", "description": "Pulitzer criteria + AP Stylebook"}, "review": {"checklist": ["Multiple independent sources", "Documents/records cited", "Subjects given right to respond", "Public interest clearly served"]}},
    "journalism/news_analysis":  {"meta": {"id": "journalism.news_analysis",  "name": "News Analysis",          "domain": "journalism", "inherits": "_base_journalism"}},
    "journalism/feature_article":{"meta": {"id": "journalism.feature_article","name": "Feature Article",        "domain": "journalism", "inherits": "_base_journalism"}},
    "journalism/op_ed":          {"meta": {"id": "journalism.op_ed",          "name": "Op-Ed / Opinion Piece",  "domain": "journalism", "inherits": "_base_journalism"}, "format": {"constraints": {"max_words": 1200}}},
    "journalism/fact_check":     {"meta": {"id": "journalism.fact_check",     "name": "Fact-Check Report",      "domain": "journalism", "inherits": "_base_journalism", "description": "IFCN Code of Principles"}, "review": {"checklist": ["Claim clearly stated", "Methodology transparent", "Sources independently verifiable", "Corrections policy visible"]}},
    "journalism/data_journalism":{"meta": {"id": "journalism.data_journalism","name": "Data Journalism Piece",  "domain": "journalism", "inherits": "_base_journalism"}},

    # ══════════════════════════════════════════════════════════════════
    # Government
    # ══════════════════════════════════════════════════════════════════
    "government/_base_government": {
        "meta": {"id": "government._base", "name": "Government Document (Base)", "domain": "government", "is_base": True},
        "format": {"constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 20}, "claim_accuracy": {"weight": 20}, "reasoning_quality": {"weight": 20}, "actionability": {"weight": 15}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 10}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0},
    },
    "government/policy_analysis":      {"meta": {"id": "government.policy_analysis",      "name": "Policy Analysis Report",      "domain": "government", "inherits": "_base_government", "description": "CBO/GAO report format"}},
    "government/intelligence_brief":   {"meta": {"id": "government.intelligence_brief",   "name": "Intelligence Brief",          "domain": "government", "inherits": "_base_government", "description": "CIA ICD 203 analytic standards"}, "review": {"checklist": ["Sources characterized by reliability", "Confidence levels stated", "Alternatives analysis included", "Key assumptions identified"]}},
    "government/environmental_impact": {"meta": {"id": "government.environmental_impact", "name": "Environmental Impact Assessment","domain": "government", "inherits": "_base_government", "description": "NEPA / EIA format"}},
    "government/budget_proposal":      {"meta": {"id": "government.budget_proposal",      "name": "Budget Proposal",             "domain": "government", "inherits": "_base_government"}},
    "government/regulatory_impact":    {"meta": {"id": "government.regulatory_impact",    "name": "Regulatory Impact Analysis",  "domain": "government", "inherits": "_base_government", "description": "OECD RIA standards"}},
    "government/public_consultation":  {"meta": {"id": "government.public_consultation",  "name": "Public Consultation Response", "domain": "government", "inherits": "_base_government"}},

    # ══════════════════════════════════════════════════════════════════
    # Marketing
    # ══════════════════════════════════════════════════════════════════
    "marketing/_base_marketing": {
        "meta": {"id": "marketing._base", "name": "Marketing Document (Base)", "domain": "marketing", "is_base": True},
        "format": {"constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 15, "description": "Data-backed claims"}, "claim_accuracy": {"weight": 15}, "reasoning_quality": {"weight": 10}, "actionability": {"weight": 20, "description": "Clear CTA"}, "uncertainty_honesty": {"weight": 5}, "structure_clarity": {"weight": 25, "description": "Readability and visual appeal"}, "counterargument_depth": {"weight": 10, "description": "Honest comparison"}}, "pass_threshold": 6.5},
    },
    "marketing/case_study":         {"meta": {"id": "marketing.case_study",         "name": "Customer Case Study",       "domain": "marketing", "inherits": "_base_marketing"}, "format": {"sections": [{"name": "challenge", "required": True}, {"name": "solution", "required": True}, {"name": "results", "required": True}]}},
    "marketing/seo_article":        {"meta": {"id": "marketing.seo_article",        "name": "SEO Long-form Article",     "domain": "marketing", "inherits": "_base_marketing", "description": "E-E-A-T compliance"}},
    "marketing/product_comparison": {"meta": {"id": "marketing.product_comparison", "name": "Product Comparison / Review","domain": "marketing", "inherits": "_base_marketing"}},
    "marketing/launch_brief":       {"meta": {"id": "marketing.launch_brief",       "name": "Product Launch Brief",      "domain": "marketing", "inherits": "_base_marketing"}},
    "marketing/email_campaign":     {"meta": {"id": "marketing.email_campaign",     "name": "Email Campaign Sequence",   "domain": "marketing", "inherits": "_base_marketing"}},
    "marketing/landing_page":       {"meta": {"id": "marketing.landing_page",       "name": "Landing Page Copy",         "domain": "marketing", "inherits": "_base_marketing", "description": "AIDA framework"}},

    # ══════════════════════════════════════════════════════════════════
    # Creative
    # ══════════════════════════════════════════════════════════════════
    "creative/_base_creative": {
        "meta": {"id": "creative._base", "name": "Creative Content (Base)", "domain": "creative", "is_base": True},
        "format": {"constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 5}, "claim_accuracy": {"weight": 5}, "reasoning_quality": {"weight": 15, "description": "Depth of insight"}, "actionability": {"weight": 10}, "uncertainty_honesty": {"weight": 5}, "structure_clarity": {"weight": 30, "description": "Readability and engagement"}, "counterargument_depth": {"weight": 30, "description": "Nuance and perspective"}}, "pass_threshold": 6.0},
    },
    "creative/blog_post":          {"meta": {"id": "creative.blog_post",          "name": "Blog Post",                "domain": "creative", "inherits": "_base_creative"}},
    "creative/newsletter":         {"meta": {"id": "creative.newsletter",         "name": "Newsletter Issue",         "domain": "creative", "inherits": "_base_creative"}},
    "creative/thought_leadership": {"meta": {"id": "creative.thought_leadership", "name": "Thought Leadership Piece", "domain": "creative", "inherits": "_base_creative"}},
    "creative/book_outline":       {"meta": {"id": "creative.book_outline",       "name": "Book Proposal / Outline",  "domain": "creative", "inherits": "_base_creative"}},
    "creative/screenplay":         {"meta": {"id": "creative.screenplay",         "name": "Screenplay / Script",      "domain": "creative", "inherits": "_base_creative"}},
    "creative/speech":             {"meta": {"id": "creative.speech",             "name": "Speech / Keynote",         "domain": "creative", "inherits": "_base_creative"}},

    # ══════════════════════════════════════════════════════════════════
    # HR / Ops
    # ══════════════════════════════════════════════════════════════════
    "hr_ops/_base_hr_ops": {
        "meta": {"id": "hr_ops._base", "name": "HR/Operations Document (Base)", "domain": "hr_ops", "is_base": True},
        "format": {"constraints": {"language": "en"}},
        "rubric": {"dimensions": {"evidence_coverage": {"weight": 10}, "claim_accuracy": {"weight": 20, "description": "Legal compliance"}, "reasoning_quality": {"weight": 15}, "actionability": {"weight": 25}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 15}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 6.5},
    },
    "hr_ops/performance_review":   {"meta": {"id": "hr_ops.performance_review",   "name": "Performance Review",        "domain": "hr_ops", "inherits": "_base_hr_ops"}, "review": {"checklist": ["SMART goals assessed", "Specific examples provided", "Development plan included"]}},
    "hr_ops/job_description":      {"meta": {"id": "hr_ops.job_description",      "name": "Job Description",           "domain": "hr_ops", "inherits": "_base_hr_ops"}},
    "hr_ops/employee_handbook":    {"meta": {"id": "hr_ops.employee_handbook",    "name": "Employee Handbook Section", "domain": "hr_ops", "inherits": "_base_hr_ops"}},
    "hr_ops/training_curriculum":  {"meta": {"id": "hr_ops.training_curriculum",  "name": "Training Curriculum Design","domain": "hr_ops", "inherits": "_base_hr_ops", "description": "ADDIE model"}},
    "hr_ops/org_restructure":      {"meta": {"id": "hr_ops.org_restructure",      "name": "Org Restructure Proposal", "domain": "hr_ops", "inherits": "_base_hr_ops"}},
    "hr_ops/compensation_analysis":{"meta": {"id": "hr_ops.compensation_analysis","name": "Compensation Analysis",    "domain": "hr_ops", "inherits": "_base_hr_ops"}},

    # ══════════════════════════════════════════════════════════════════
    # General (original + expanded)
    # ══════════════════════════════════════════════════════════════════
    "general/decision":     {"meta": {"id": "general.decision",     "name": "Decision Pack",      "domain": "general"}, "format": {"sections": [{"name": "conclusion", "required": True}, {"name": "reasoning", "required": True}, {"name": "counterarguments", "required": True}, {"name": "uncertainties", "required": True}, {"name": "action_items", "required": True}, {"name": "sources", "required": True}]}, "rubric": {"dimensions": {"evidence_coverage": {"weight": 25}, "claim_accuracy": {"weight": 20}, "reasoning_quality": {"weight": 15}, "actionability": {"weight": 20}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 5}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0}},
    "general/proposal":     {"meta": {"id": "general.proposal",     "name": "Proposal Pack",      "domain": "general"}, "format": {"sections": [{"name": "executive_summary", "required": True}, {"name": "problem", "required": True}, {"name": "solution", "required": True}, {"name": "implementation", "required": True}, {"name": "risks", "required": True}, {"name": "resources", "required": True}, {"name": "sources", "required": True}]}, "rubric": {"dimensions": {"evidence_coverage": {"weight": 20}, "claim_accuracy": {"weight": 15}, "reasoning_quality": {"weight": 15}, "actionability": {"weight": 25}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 10}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0}},
    "general/comparison":   {"meta": {"id": "general.comparison",   "name": "Comparison Pack",    "domain": "general"}, "format": {"sections": [{"name": "summary", "required": True}, {"name": "comparison_matrix", "required": True}, {"name": "detailed_analysis", "required": True}, {"name": "recommendation", "required": True}, {"name": "sources", "required": True}]}, "rubric": {"dimensions": {"evidence_coverage": {"weight": 25}, "claim_accuracy": {"weight": 20}, "reasoning_quality": {"weight": 15}, "actionability": {"weight": 10}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 10}, "counterargument_depth": {"weight": 10}}, "pass_threshold": 7.0}},
    "general/brief":        {"meta": {"id": "general.brief",        "name": "Brief Pack",         "domain": "general"}, "format": {"sections": [{"name": "summary", "required": True}, {"name": "key_points", "required": True}, {"name": "details", "required": True}, {"name": "implications", "required": True}, {"name": "sources", "required": True}]}, "rubric": {"dimensions": {"evidence_coverage": {"weight": 20}, "claim_accuracy": {"weight": 20}, "reasoning_quality": {"weight": 15}, "actionability": {"weight": 15}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 15}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0}},
    "general/study":        {"meta": {"id": "general.study",        "name": "Study Pack",         "domain": "general"}, "format": {"sections": [{"name": "executive_summary", "required": True}, {"name": "methodology", "required": True}, {"name": "findings", "required": True}, {"name": "analysis", "required": True}, {"name": "limitations", "required": True}, {"name": "conclusions", "required": True}, {"name": "sources", "required": True}]}, "rubric": {"dimensions": {"evidence_coverage": {"weight": 30}, "claim_accuracy": {"weight": 25}, "reasoning_quality": {"weight": 15}, "actionability": {"weight": 5}, "uncertainty_honesty": {"weight": 10}, "structure_clarity": {"weight": 10}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 7.0}},
    "general/how_to":       {"meta": {"id": "general.how_to",       "name": "How-To Guide",       "domain": "general"}, "format": {"sections": [{"name": "overview", "required": True}, {"name": "prerequisites", "required": True}, {"name": "steps", "required": True}, {"name": "troubleshooting", "required": False}]}, "rubric": {"dimensions": {"evidence_coverage": {"weight": 10}, "claim_accuracy": {"weight": 15}, "reasoning_quality": {"weight": 10}, "actionability": {"weight": 35}, "uncertainty_honesty": {"weight": 5}, "structure_clarity": {"weight": 20}, "counterargument_depth": {"weight": 5}}, "pass_threshold": 6.5}},
    "general/pros_cons":    {"meta": {"id": "general.pros_cons",    "name": "Pros & Cons Analysis","domain": "general"}, "rubric": {"pass_threshold": 6.5}},
    "general/explainer":    {"meta": {"id": "general.explainer",    "name": "Concept Explainer",  "domain": "general"}, "rubric": {"pass_threshold": 6.5}},
    "general/daily_digest": {"meta": {"id": "general.daily_digest", "name": "Daily/Weekly Digest","domain": "general"}, "rubric": {"pass_threshold": 6.0}},
    "general/meeting_prep": {"meta": {"id": "general.meeting_prep", "name": "Meeting Prep Pack",  "domain": "general"}, "rubric": {"pass_threshold": 6.0}},
}


def main():
    count = 0
    for rel_path, data in PROFILES.items():
        path = PROFILES_DIR / f"{rel_path}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)
        count += 1

    print(f"✅ Generated {count} profile YAML files in {PROFILES_DIR}")

    # Count by domain
    domains = {}
    for rel_path in PROFILES:
        d = rel_path.split("/")[0]
        if "_base" not in rel_path.split("/")[1]:
            domains[d] = domains.get(d, 0) + 1
    for d, c in sorted(domains.items()):
        print(f"   {d:20s}: {c} profiles")

    total_scene = sum(domains.values())
    print(f"   {'TOTAL':20s}: {total_scene} scene profiles + {count - total_scene} base profiles")


if __name__ == "__main__":
    main()

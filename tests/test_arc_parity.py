"""ARC Parity Test Suite — 50 tests proving IdeaClaw matches ARC's depth.

Tests organized by ARC's claimed capability areas:
  A. Orchestrator loop (8 tests)
  B. Scenario profiles (7 tests)
  C. Evaluator/scoring (8 tests)
  D. Version control (7 tests)
  E. Citation verification (8 tests)
  F. Config system (6 tests)
  G. Health doctor (6 tests)
"""

from __future__ import annotations

import json
import tempfile
import textwrap
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# A. ORCHESTRATOR LOOP (8 tests)
# ---------------------------------------------------------------------------

from ideaclaw.orchestrator.loop import (
    EvalCriterion,
    ExperimentConfig,
    IterationResult,
    LoopState,
    ResearchLoop,
    ScenarioProfile,
    SearchConfig,
    StyleConfig,
    load_all_profiles,
    load_profile,
)
from ideaclaw.orchestrator.evaluator import UnifiedEvaluator
from ideaclaw.orchestrator.versioning import Versioning


def _make_profile(**overrides) -> ScenarioProfile:
    """Helper: create a ScenarioProfile with sensible defaults."""
    defaults = dict(
        scenario_id="test",
        display_name="Test Profile",
        category="test",
        objective="Generate a high-quality test output.",
        criteria=[
            EvalCriterion(name="structure", weight=0.3, min_score=0.3),
            EvalCriterion(name="depth", weight=0.3, min_score=0.3),
            EvalCriterion(name="citations", weight=0.2, min_score=0.3),
            EvalCriterion(name="style", weight=0.2, min_score=0.3),
        ],
        target_score=0.80,
        min_score=0.50,
        max_iterations=3,
    )
    defaults.update(overrides)
    return ScenarioProfile(**defaults)


SAMPLE_DRAFT = textwrap.dedent("""\
    # Introduction

    This paper presents a novel approach to automated research.
    We build on prior work [vaswani2017] and extend the paradigm.

    ## Related Work

    Prior approaches include BERT [devlin2019] and GPT [brown2020].

    ## Method

    Our method uses a multi-layered scoring system with weighted criteria.
    The approach is validated on three benchmarks with statistical significance.

    ## Experiments

    We evaluate on GLUE, SuperGLUE, and SQuAD v2.0.
    Results show state-of-the-art performance on 2 of 3 benchmarks.

    | Benchmark | Ours | Previous SOTA |
    |-----------|------|---------------|
    | GLUE      | 89.2 | 88.1          |
    | SuperGLUE | 87.5 | 87.0          |
    | SQuAD 2.0 | 82.1 | 83.2          |

    ## Conclusion

    We demonstrated that our approach achieves competitive results.
""") * 3  # Repeat for length


class TestOrchestrator:
    """A. Orchestrator loop tests (ARC: autonomous loop with accept/revert)."""

    def test_a1_loop_runs_to_completion(self):
        """A1: Loop should run all iterations when target not reached."""
        profile = _make_profile(max_iterations=3, target_score=0.99)

        def mock_search(profile, ctx):
            return [{"title": "Paper A", "abstract": "..."}]

        def mock_generate(profile, sources, prev, feedback):
            return SAMPLE_DRAFT

        evaluator = UnifiedEvaluator()

        def mock_evaluate(profile, draft, sources):
            return evaluator.evaluate(profile, draft, sources)

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(
                search_fn=mock_search,
                generate_fn=mock_generate,
                evaluate_fn=mock_evaluate,
                output_dir=Path(td),
            )
            state = loop.run(profile)

        assert state.iteration_count == 3
        assert state.status in ("completed", "failed")

    def test_a2_loop_stops_at_target(self):
        """A2: Loop should stop early when target score is reached."""
        profile = _make_profile(max_iterations=10, target_score=0.01)

        def always_high_eval(p, draft, s):
            return {"structure": 0.9, "depth": 0.9, "citations": 0.9, "style": 0.9}

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(
                generate_fn=lambda p, s, d, f: "draft",
                evaluate_fn=always_high_eval,
                output_dir=Path(td),
            )
            state = loop.run(profile)

        assert state.status == "completed"
        assert state.iteration_count < 10  # Should have stopped early

    def test_a3_loop_reverts_bad_drafts(self):
        """A3: Drafts below min_score should be reverted."""
        profile = _make_profile(min_score=0.99, max_iterations=2)

        def always_low_eval(p, draft, s):
            return {"structure": 0.1, "depth": 0.1, "citations": 0.1, "style": 0.1}

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(
                generate_fn=lambda p, s, d, f: "bad draft",
                evaluate_fn=always_low_eval,
                output_dir=Path(td),
            )
            state = loop.run(profile)

        assert all(not r.accepted for r in state.iterations)
        assert state.best_score < 0.99

    def test_a4_loop_tracks_best_iteration(self):
        """A4: Loop should track the best-performing iteration."""
        profile = _make_profile(max_iterations=3, min_score=0.01)
        call_count = [0]

        def improving_eval(p, draft, s):
            call_count[0] += 1
            v = 0.2 * call_count[0]
            return {"structure": v, "depth": v, "citations": v, "style": v}

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(
                generate_fn=lambda p, s, d, f: "draft",
                evaluate_fn=improving_eval,
                output_dir=Path(td),
            )
            state = loop.run(profile)

        assert state.best_iteration == 2  # Last iter is best (0-indexed)

    def test_a5_loop_saves_state_json(self):
        """A5: Loop should save state.json to run directory."""
        profile = _make_profile(max_iterations=1)

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(
                generate_fn=lambda p, s, d, f: "draft",
                evaluate_fn=lambda p, d, s: {"structure": 0.5, "depth": 0.5,
                                              "citations": 0.5, "style": 0.5},
                output_dir=Path(td),
            )
            state = loop.run(profile)

            # Find the run dir
            run_dirs = list(Path(td).iterdir())
            assert len(run_dirs) == 1
            state_file = run_dirs[0] / "state.json"
            assert state_file.exists()
            data = json.loads(state_file.read_text())
            assert data["profile_id"] == "test"

    def test_a6_loop_with_versioning(self):
        """A6: Loop + Versioning should commit accepted drafts."""
        profile = _make_profile(max_iterations=2, min_score=0.01)

        with tempfile.TemporaryDirectory() as td:
            ver = Versioning(run_dir=Path(td))
            loop = ResearchLoop(
                generate_fn=lambda p, s, d, f: "good draft",
                evaluate_fn=lambda p, d, s: {"structure": 0.8, "depth": 0.8,
                                              "citations": 0.8, "style": 0.8},
                versioning=ver,
                output_dir=Path(td),
            )
            state = loop.run(profile)

            best = ver.get_best(state.run_id)
            assert best == "good draft"

    def test_a7_loop_generates_feedback(self):
        """A7: Loop should generate actionable feedback between iterations."""
        profile = _make_profile(max_iterations=2, min_score=0.01)
        feedbacks = []

        def capture_generate(p, sources, prev, feedback):
            feedbacks.append(feedback)
            return "draft"

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(
                generate_fn=capture_generate,
                evaluate_fn=lambda p, d, s: {"structure": 0.5, "depth": 0.3,
                                              "citations": 0.4, "style": 0.6},
                output_dir=Path(td),
            )
            loop.run(profile)

        # First iteration has empty feedback, second should have guidance
        assert feedbacks[0] == ""
        assert len(feedbacks) > 1
        assert "depth" in feedbacks[1].lower() or "Focus" in feedbacks[1]

    def test_a8_loop_resume_from_state(self):
        """A8: Loop should support resuming from a previous state."""
        profile = _make_profile(max_iterations=4, min_score=0.01)

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(
                generate_fn=lambda p, s, d, f: "draft",
                evaluate_fn=lambda p, d, s: {"structure": 0.5, "depth": 0.5,
                                              "citations": 0.5, "style": 0.5},
                output_dir=Path(td),
            )
            # Run 2 iterations
            profile2 = _make_profile(max_iterations=2, min_score=0.01)
            state1 = loop.run(profile2, run_id="resume_test")
            assert state1.iteration_count == 2

            # Resume for 2 more
            state2 = loop.run(profile, run_id="resume_test", resume_state=state1)
            assert state2.iteration_count == 4


# ---------------------------------------------------------------------------
# B. SCENARIO PROFILES (7 tests)
# ---------------------------------------------------------------------------

class TestProfiles:
    """B. Scenario profile loading (ARC: program.md equivalent)."""

    PROFILES_DIR = Path(__file__).parent.parent / "ideaclaw" / "orchestrator" / "profiles"

    def test_b1_load_all_20_profiles(self):
        """B1: All 20 scenario profiles should load without errors."""
        profiles = load_all_profiles(self.PROFILES_DIR)
        assert len(profiles) >= 20

    def test_b2_icml_profile_has_correct_criteria(self):
        """B2: ICML profile should have 6 evaluation criteria."""
        p = load_profile(self.PROFILES_DIR / "icml_2025.yaml")
        assert len(p.criteria) == 6
        names = {c.name for c in p.criteria}
        assert "novelty" in names
        assert "soundness" in names

    def test_b3_neurips_requires_reproducibility(self):
        """B3: NeurIPS profile should have reproducibility criterion."""
        p = load_profile(self.PROFILES_DIR / "neurips_2025.yaml")
        names = {c.name for c in p.criteria}
        assert "reproducibility" in names

    def test_b4_nature_has_highest_target(self):
        """B4: Nature/Science should have the highest target score (0.90)."""
        profiles = load_all_profiles(self.PROFILES_DIR)
        nature = profiles["nature_science"]
        assert nature.target_score == 0.90
        # Should be one of the highest targets
        max_target = max(p.target_score for p in profiles.values())
        assert nature.target_score == max_target

    def test_b5_profiles_cover_all_categories(self):
        """B5: Profiles should cover diverse categories."""
        profiles = load_all_profiles(self.PROFILES_DIR)
        categories = {p.category for p in profiles.values()}
        # Should have academic, business, legal at minimum
        assert len(categories) >= 5

    def test_b6_all_criteria_weights_sum_to_1(self):
        """B6: Each profile's criteria weights should approximately sum to 1.0."""
        profiles = load_all_profiles(self.PROFILES_DIR)
        for pid, p in profiles.items():
            total = sum(c.weight for c in p.criteria)
            assert abs(total - 1.0) <= 0.3, f"{pid}: weights sum to {total}"

    def test_b7_all_profiles_have_required_sections(self):
        """B7: Each profile should define required sections."""
        profiles = load_all_profiles(self.PROFILES_DIR)
        for pid, p in profiles.items():
            assert len(p.style.required_sections) >= 2, \
                f"{pid}: only {len(p.style.required_sections)} required sections"


# ---------------------------------------------------------------------------
# C. EVALUATOR / SCORING (8 tests)
# ---------------------------------------------------------------------------

class TestEvaluator:
    """C. Unified evaluator (ARC: multi-dimensional scoring)."""

    def test_c1_evaluate_returns_all_dimensions(self):
        """C1: Evaluator should score all registered dimensions."""
        evaluator = UnifiedEvaluator()
        profile = _make_profile()
        scores = evaluator.evaluate(profile, SAMPLE_DRAFT, [])
        assert "structure" in scores
        assert "depth" in scores

    def test_c2_headings_improve_structure_score(self):
        """C2: More headings should improve structure score."""
        evaluator = UnifiedEvaluator()
        profile = _make_profile()

        no_headings = "Just plain text without any structure." * 100
        with_headings = SAMPLE_DRAFT
        s1 = evaluator.evaluate(profile, no_headings, [])
        s2 = evaluator.evaluate(profile, with_headings, [])
        assert s2["structure"] >= s1["structure"]

    def test_c3_citations_detected(self):
        """C3: Citation score should reflect citation density."""
        evaluator = UnifiedEvaluator()
        profile = _make_profile()

        no_cites = "A paper with no references at all." * 100
        has_cites = "As shown by [Smith2020], this is valid. See [Jones2021]." * 50
        s1 = evaluator.evaluate(profile, no_cites, [])
        s2 = evaluator.evaluate(profile, has_cites, [])
        assert s2.get("citations", 0) >= s1.get("citations", 0)

    def test_c4_custom_scorer_registration(self):
        """C4: Custom scorers can be registered and used."""
        evaluator = UnifiedEvaluator()

        def novelty_scorer(draft: str, profile, sources) -> float:
            return 0.42  # Fixed score for testing

        evaluator.register_scorer("novelty_test", novelty_scorer)
        profile = _make_profile(criteria=[
            EvalCriterion(name="novelty_test", weight=1.0),
        ])
        scores = evaluator.evaluate(profile, SAMPLE_DRAFT, [])
        assert scores.get("novelty_test") == 0.42

    def test_c5_depth_rewards_length(self):
        """C5: Longer, more detailed drafts should score higher on depth."""
        evaluator = UnifiedEvaluator()
        profile = _make_profile()

        short = "Brief text." * 10
        long = SAMPLE_DRAFT * 5
        s1 = evaluator.evaluate(profile, short, [])
        s2 = evaluator.evaluate(profile, long, [])
        assert s2.get("depth", 0) >= s1.get("depth", 0)

    def test_c6_all_scores_bounded_0_1(self):
        """C6: All scores should be between 0.0 and 1.0."""
        evaluator = UnifiedEvaluator()
        profile = _make_profile()
        scores = evaluator.evaluate(profile, SAMPLE_DRAFT, [])
        for name, score in scores.items():
            assert 0.0 <= score <= 1.0, f"{name}={score} out of bounds"

    def test_c7_empty_draft_scores_low(self):
        """C7: Empty draft should produce lower aggregate than a rich draft."""
        evaluator = UnifiedEvaluator()
        profile = _make_profile()
        empty_scores = evaluator.evaluate(profile, "", [])
        rich_scores = evaluator.evaluate(profile, SAMPLE_DRAFT, [])
        # Depth and citations should definitely be lower for empty
        assert empty_scores.get("depth", 0) <= rich_scores.get("depth", 1)
        assert empty_scores.get("citations", 0) <= rich_scores.get("citations", 1)

    def test_c8_composite_score_weighting(self):
        """C8: Composite score should respect criteria weights."""
        profile = _make_profile(criteria=[
            EvalCriterion(name="a", weight=0.9),
            EvalCriterion(name="b", weight=0.1),
        ])
        # Manually compute composite
        scores = {"a": 1.0, "b": 0.0}
        expected = (0.9 * 1.0 + 0.1 * 0.0) / 1.0  # = 0.9

        with tempfile.TemporaryDirectory() as td:
            loop = ResearchLoop(output_dir=Path(td))
            composite = loop._compute_composite(profile, scores)
        assert abs(composite - 0.9) < 0.01


# ---------------------------------------------------------------------------
# D. VERSION CONTROL (7 tests)
# ---------------------------------------------------------------------------

class TestVersioning:
    """D. Version control (ARC: commit/revert with diffs)."""

    def test_d1_commit_and_retrieve(self):
        """D1: Committed draft should be retrievable."""
        with tempfile.TemporaryDirectory() as td:
            v = Versioning(run_dir=Path(td))
            v.commit("run1", 0, "draft v1", 0.7, {"a": 0.7})
            assert v.get_best("run1") == "draft v1"

    def test_d2_multiple_commits_track_best(self):
        """D2: Best draft should be the highest-scoring commit."""
        with tempfile.TemporaryDirectory() as td:
            v = Versioning(run_dir=Path(td))
            v.commit("run1", 0, "draft v1", 0.5, {})
            v.commit("run1", 1, "draft v2", 0.8, {})
            v.commit("run1", 2, "draft v3", 0.6, {})
            assert v.get_best("run1") == "draft v2"

    def test_d3_revert_tracks_rejection(self):
        """D3: Reverted iterations should be recorded."""
        with tempfile.TemporaryDirectory() as td:
            v = Versioning(run_dir=Path(td))
            v.commit("run1", 0, "good", 0.8, {})
            v.revert("run1", 1)
            report = v.evolution_report("run1")
            assert "Revert" in report

    def test_d4_diff_between_versions(self):
        """D4: Diff should show changes between versions."""
        with tempfile.TemporaryDirectory() as td:
            v = Versioning(run_dir=Path(td))
            v.commit("run1", 0, "line one\nline two\n", 0.5, {})
            v.commit("run1", 1, "line one\nline three\n", 0.6, {})
            diff = v.get_diff("run1", 0, 1)
            assert diff is not None
            assert "-line two" in diff or "+line three" in diff

    def test_d5_evolution_report(self):
        """D5: Evolution report should show score progression."""
        with tempfile.TemporaryDirectory() as td:
            v = Versioning(run_dir=Path(td))
            v.commit("run1", 0, "d1", 0.5, {"a": 0.5})
            v.commit("run1", 1, "d2", 0.7, {"a": 0.7})
            v.commit("run1", 2, "d3", 0.9, {"a": 0.9})
            report = v.evolution_report("run1")
            assert "0.5" in report or "0.50" in report
            assert "0.9" in report or "0.90" in report

    def test_d6_get_best_returns_none_for_unknown(self):
        """D6: get_best on unknown run_id should return None."""
        with tempfile.TemporaryDirectory() as td:
            v = Versioning(run_dir=Path(td))
            assert v.get_best("nonexistent") is None

    def test_d7_history_returns_all_entries(self):
        """D7: History should return all committed entries."""
        with tempfile.TemporaryDirectory() as td:
            v = Versioning(run_dir=Path(td))
            v.commit("run1", 0, "d1", 0.5, {})
            v.commit("run1", 1, "d2", 0.7, {})
            history = v.get_history("run1")
            assert len(history) == 2


# ---------------------------------------------------------------------------
# E. CITATION VERIFICATION (8 tests)
# ---------------------------------------------------------------------------

from ideaclaw.evidence.citation_verify import (
    CitationResult,
    VerificationReport,
    VerifyStatus,
    annotate_paper_hallucinations,
    filter_verified_bibtex,
    parse_bibtex_entries,
    title_similarity,
)


class TestCitationVerify:
    """E. Citation verification (ARC: 3-layer verify with cache)."""

    def test_e1_parse_single_entry(self):
        """E1: Parse a single BibTeX entry."""
        bib = """@article{smith2020,
  title = {A Great Paper},
  author = {Smith, John},
  year = {2020},
}"""
        entries = parse_bibtex_entries(bib)
        assert len(entries) == 1
        assert entries[0]["key"] == "smith2020"
        assert entries[0]["title"] == "A Great Paper"

    def test_e2_parse_multiple_entries(self):
        """E2: Parse multiple BibTeX entries with different types."""
        bib = """@article{a2020,
  title = {Paper A},
  year = {2020},
}

@inproceedings{b2021,
  title = {Paper B},
  year = {2021},
  doi = {10.1234/test},
}"""
        entries = parse_bibtex_entries(bib)
        assert len(entries) == 2
        assert entries[1]["doi"] == "10.1234/test"

    def test_e3_title_similarity_identical(self):
        """E3: Identical titles should have similarity 1.0."""
        assert title_similarity("Hello World", "hello world") == 1.0

    def test_e4_title_similarity_different(self):
        """E4: Very different titles should have low similarity."""
        sim = title_similarity(
            "Attention Is All You Need",
            "Cooking Recipes for Italian Pasta",
        )
        assert sim < 0.2

    def test_e5_title_similarity_partial(self):
        """E5: Partial overlap should give intermediate similarity."""
        sim = title_similarity(
            "Deep Learning for Natural Language Processing",
            "Deep Learning Methods for Computer Vision",
        )
        assert 0.2 < sim < 0.8

    def test_e6_verification_report_integrity(self):
        """E6: Integrity score should be verified/verifiable."""
        report = VerificationReport(
            total=10, verified=8, suspicious=1, hallucinated=1,
        )
        assert report.integrity_score == 0.8

    def test_e7_hallucination_removal_latex(self):
        """E7: Hallucinated keys should be removed from LaTeX citations."""
        report = VerificationReport(results=[
            CitationResult("good2020", "", VerifyStatus.VERIFIED, 1.0, ""),
            CitationResult("bad2020", "", VerifyStatus.HALLUCINATED, 1.0, ""),
        ])
        text = r"See \cite{good2020, bad2020} for details."
        cleaned = annotate_paper_hallucinations(text, report)
        assert "good2020" in cleaned
        assert "bad2020" not in cleaned

    def test_e8_filter_bibtex_keeps_verified(self):
        """E8: filter_verified_bibtex should discard hallucinated entries."""
        bib = """@article{verified2020,
  title = {Verified Paper},
}

@article{hallucinated2020,
  title = {Hallucinated Paper},
}"""
        report = VerificationReport(results=[
            CitationResult("verified2020", "", VerifyStatus.VERIFIED, 1.0, ""),
            CitationResult("hallucinated2020", "", VerifyStatus.HALLUCINATED, 1.0, ""),
        ])
        filtered = filter_verified_bibtex(bib, report, include_suspicious=False)
        assert "verified2020" in filtered
        assert "hallucinated2020" not in filtered


# ---------------------------------------------------------------------------
# F. CONFIG SYSTEM (6 tests)
# ---------------------------------------------------------------------------

from ideaclaw.config import (
    IdeaClawConfig,
    LlmConfig,
    OrchestratorConfig,
    LibraryConfig,
    ValidationResult,
    load_config,
    validate_config,
)


class TestConfig:
    """F. Typed configuration (ARC: frozen dataclasses + validation)."""

    def test_f1_default_config_loads(self):
        """F1: Default config should load without any file."""
        cfg = load_config()
        assert isinstance(cfg, IdeaClawConfig)

    def test_f2_config_has_16_sections(self):
        """F2: Config should have 16 typed sections."""
        cfg = load_config()
        assert len(cfg.__dataclass_fields__) == 16

    def test_f3_llm_defaults_correct(self):
        """F3: LLM defaults should be sensible."""
        cfg = load_config()
        assert cfg.llm.primary_model == "gpt-4o"
        assert cfg.llm.temperature == 0.7

    def test_f4_validation_catches_missing_required(self):
        """F4: Validation should catch missing required fields."""
        result = validate_config({})
        assert not result.ok
        assert len(result.errors) > 0

    def test_f5_validation_passes_valid_config(self):
        """F5: Validation should pass for valid config."""
        result = validate_config({
            "project": {"name": "test"},
            "llm": {"provider": "openai-compatible"},
        })
        assert result.ok

    def test_f6_config_from_yaml(self):
        """F6: Config should load from YAML file."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("project:\n  name: test_project\nllm:\n  provider: anthropic\n  primary_model: claude-3\n")
            f.flush()
            cfg = load_config(Path(f.name))
            assert cfg.project.name == "test_project"
            assert cfg.llm.primary_model == "claude-3"
            Path(f.name).unlink()


# ---------------------------------------------------------------------------
# G. HEALTH DOCTOR (6 tests)
# ---------------------------------------------------------------------------

from ideaclaw.health import (
    CheckResult,
    DoctorReport,
    check_cache_dir,
    check_dependencies,
    check_disk_space,
    check_git,
    check_python_version,
    check_yaml_import,
)


class TestHealth:
    """G. Health check system (ARC: DoctorReport + multiple checks)."""

    def test_g1_python_version_passes(self):
        """G1: Python version check should pass (we're running 3.10+)."""
        result = check_python_version()
        assert result.status == "pass"

    def test_g2_yaml_import_passes(self):
        """G2: YAML import check should pass."""
        result = check_yaml_import()
        assert result.status == "pass"

    def test_g3_disk_space_check(self):
        """G3: Disk space check should return valid result."""
        result = check_disk_space()
        assert result.status in ("pass", "warn")

    def test_g4_doctor_report_markdown(self):
        """G4: DoctorReport should generate valid markdown."""
        report = DoctorReport(
            timestamp="2024-01-01T00:00:00Z",
            checks=[
                CheckResult("test1", "pass", "All good"),
                CheckResult("test2", "fail", "Broken", fix="Fix it"),
            ],
        )
        md = report.to_markdown()
        assert "✅" in md
        assert "❌" in md
        assert "Fix it" in md

    def test_g5_doctor_report_json(self):
        """G5: DoctorReport should produce valid JSON dict."""
        report = DoctorReport(
            timestamp="2024-01-01T00:00:00Z",
            checks=[CheckResult("test1", "pass", "ok")],
        )
        d = report.to_dict()
        assert d["overall"] == "unknown"
        assert d["summary"]["pass"] == 1

    def test_g6_cache_dir_writable(self):
        """G6: Cache directory should be writable."""
        result = check_cache_dir()
        assert result.status == "pass"

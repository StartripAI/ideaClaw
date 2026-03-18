"""T8: Export + sandbox tests (5 tests).

Tests LaTeX NeurIPS export, BibTeX generation, DOCX tracked-change
tokenization, sandbox code execution, and experiment evaluator.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from ideaclaw.export.latex import LaTeXExporter
from ideaclaw.export.revise_docx import tokenize_replacement
from ideaclaw.sandbox.executor import SandboxExecutor, SandboxConfig, ExecResult
from ideaclaw.sandbox.evaluator import ExperimentEvaluator, EvalResult


# ---- T8.1: LaTeX NeurIPS export ----
def test_t8_1_latex_neurips(tmp_dir):
    """T8.1: LaTeX NeurIPS should produce .tex with sections and tabular."""
    md = (
        "# Introduction\nTest **bold** paper.\n\n"
        "## Methods\n- Step 1\n- Step 2\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n"
    )
    exporter = LaTeXExporter("neurips")
    tex_path = tmp_dir / "paper.tex"
    exporter.export(
        md, tex_path,
        metadata={"title": "Test Paper", "authors": ["Author A"]},
        sources=[{"title": "Ref 1", "doi": "10.123/test", "year": "2024"}],
    )
    tex = tex_path.read_text()
    assert "neurips" in tex, "Should contain neurips preamble"
    assert "\\section" in tex, "Should have \\section"
    assert "tabular" in tex, "Should have tabular environment"


# ---- T8.2: BibTeX generation ----
def test_t8_2_bibtex_generation(tmp_dir):
    """T8.2: BibTeX should contain entries with DOIs."""
    exporter = LaTeXExporter("generic")
    tex_path = tmp_dir / "paper.tex"
    sources = [
        {"title": "Paper A", "doi": "10.111/aaa", "authors": "Smith", "year": "2023"},
        {"title": "Paper B", "doi": "10.222/bbb", "authors": "Jones", "year": "2024"},
        {"title": "Paper C", "doi": "10.333/ccc", "authors": "Wang", "year": "2025"},
    ]
    exporter.export("# Test", tex_path, sources=sources)
    bib_path = tex_path.with_suffix(".bib")
    assert bib_path.exists(), ".bib file should be created"
    bib = bib_path.read_text()
    assert bib.count("@article") == 3, f"Should have 3 entries, got {bib.count('@article')}"
    assert "10.111/aaa" in bib
    assert "10.333/ccc" in bib


# ---- T8.3: DOCX tracked-change tokenizer ----
def test_t8_3_docx_tokenizer():
    """T8.3: tokenize_replacement should parse footnote tokens."""
    tokens = tokenize_replacement("Updated text[[fn:src1]] per evidence[[fnid:42]]")
    assert len(tokens) == 4, f"Expected 4 tokens, got {len(tokens)}: {tokens}"
    types = [t[0] for t in tokens]
    assert "text" in types
    assert "footnote_new" in types
    assert "footnote_existing" in types
    # Check values
    fn_new = [t for t in tokens if t[0] == "footnote_new"]
    assert fn_new[0][1] == "src1"
    fn_exist = [t for t in tokens if t[0] == "footnote_existing"]
    assert fn_exist[0][1] == "42"


# ---- T8.4: Sandbox execution ----
def test_t8_4_sandbox_execution():
    """T8.4: Sandbox should execute Python script and extract metrics."""
    executor = SandboxExecutor(SandboxConfig(timeout_seconds=10))
    try:
        result = executor.run_script(
            "experiment.py",
            'import json\nprint("Running experiment...")\nprint(json.dumps({"val_bpb": 1.234, "loss": 0.567}))\n',
        )
        assert result.success, f"Script should succeed: {result.stderr}"
        assert result.exit_code == 0
        assert result.metrics.get("val_bpb") == 1.234, f"Metrics: {result.metrics}"
        assert result.metrics.get("loss") == 0.567
        assert result.elapsed_seconds > 0
    finally:
        executor.cleanup()


# ---- T8.5: Experiment evaluator ----
def test_t8_5_experiment_evaluator():
    """T8.5: Evaluator should ACCEPT when primary metric improves."""
    evaluator = ExperimentEvaluator(
        primary_metric="val_bpb",
        direction="minimize",
        min_improvement_pct=0.1,
    )

    baseline = ExecResult(
        success=True, exit_code=0, stdout="", stderr="",
        elapsed_seconds=5.0, metrics={"val_bpb": 1.500, "train_loss": 0.8},
    )
    experiment = ExecResult(
        success=True, exit_code=0, stdout="", stderr="",
        elapsed_seconds=5.0, metrics={"val_bpb": 1.200, "train_loss": 0.6},
    )

    result = evaluator.compare(baseline, experiment)
    assert result.decision == "ACCEPT", f"Expected ACCEPT, got {result.decision}: {result.reason}"
    assert result.improvement["val_bpb"] < 0, "Should show negative % change (minimize)"
    assert result.significant

    # Test REJECT case
    worse = ExecResult(
        success=True, exit_code=0, stdout="", stderr="",
        elapsed_seconds=5.0, metrics={"val_bpb": 1.800},
    )
    reject_result = evaluator.compare(baseline, worse)
    assert reject_result.decision == "REJECT", f"Expected REJECT, got {reject_result.decision}"

    # Test failed experiment
    failed = ExecResult(
        success=False, exit_code=1, stdout="", stderr="OOM",
        elapsed_seconds=5.0, metrics={}, error="out_of_memory",
    )
    fail_result = evaluator.compare(baseline, failed)
    assert fail_result.decision == "REJECT", f"Failed experiment should be REJECTED"

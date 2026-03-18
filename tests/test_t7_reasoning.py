"""T7: Reasoning module tests (5 tests).

Tests MECE decomposition, decision tree, counterarguments,
multi-agent debate (heuristic), and debate single-prompt generation.
"""

from __future__ import annotations

import pytest
from ideaclaw.reasoning.decompose import heuristic_decompose
from ideaclaw.reasoning.synthesize import heuristic_synthesize
from ideaclaw.reasoning.decision_tree import build_decision_tree, DecisionNode
from ideaclaw.reasoning.counterarguments import generate_heuristic_counterarguments
from ideaclaw.reasoning.debate import (
    DebateOrchestrator,
    STANDARD_DEBATE_TEAM,
)


# ---- T7.1: MECE decomposition ----
def test_t7_1_mece_decomposition():
    """T7.1: Should generate ≥5 sub-questions using 5W1H."""
    sqs = heuristic_decompose("Should I invest in a coffee shop franchise?")
    assert len(sqs) >= 5, f"Expected ≥5 sub-questions, got {len(sqs)}"
    # Check diversity (not all the same)
    unique = set(sq.lower()[:30] for sq in sqs)
    assert len(unique) >= 4, "Sub-questions should be diverse"


# ---- T7.2: Decision tree ----
def test_t7_2_decision_tree():
    """T7.2: Decision tree should have branches and produce valid markdown."""
    sqs = heuristic_decompose("Should I invest in X?")
    synth = heuristic_synthesize(
        [{"claim": "Market growing 10%", "confidence": "HIGH", "source": "Report"}],
        "Investment analysis",
    )
    tree = build_decision_tree("Should I invest?", sqs, synth)
    assert isinstance(tree, DecisionNode)
    assert len(tree.children) > 0, "Tree should have at least one branch"
    md = tree.to_markdown()
    assert len(md) > 50, f"Markdown too short: {len(md)} chars"
    assert "invest" in md.lower()


# ---- T7.3: Counterarguments ----
def test_t7_3_counterarguments():
    """T7.3: Should generate ≥3 counterarguments covering multiple categories."""
    counters = generate_heuristic_counterarguments(
        "We should invest $10M in a new AI startup"
    )
    assert len(counters) >= 3, f"Expected ≥3 counterarguments, got {len(counters)}"
    categories = set(c.category for c in counters)
    assert len(categories) >= 2, f"Should cover ≥2 categories, got {categories}"


# ---- T7.4: Multi-agent debate (heuristic) ----
def test_t7_4_debate_heuristic():
    """T7.4: Heuristic debate should produce votes and a verdict."""
    debate = DebateOrchestrator(max_rounds=1)
    result = debate.debate_heuristic(
        "AI will always outperform humans at every task",
        evidence=[
            {"title": "Study A", "source": "Nature", "text": "AI beats humans at chess"},
        ],
    )
    assert result.final_verdict in ("CONSENSUS_SUPPORT", "CONSENSUS_OPPOSE", "NO_CONSENSUS")
    assert result.consensus_strength > 0
    assert len(result.messages) > 0
    # "always" and "every" are absolute terms — Devil's Advocate should OPPOSE
    assert result.vote_tally.get("OPPOSE", 0) >= 1, \
        f"Devil's Advocate should oppose absolute claims: {result.vote_tally}"


# ---- T7.5: Debate single-prompt ----
def test_t7_5_debate_single_prompt():
    """T7.5: Single-prompt should contain all agent roles and protocol."""
    debate = DebateOrchestrator(max_rounds=2)
    prompt = debate.build_debate_prompt_for_external_llm(
        "Quantum computing will replace classical computing by 2035"
    )
    assert "Multi-Agent Debate" in prompt
    assert "Domain Expert" in prompt
    assert "Devil's Advocate" in prompt
    assert "SUPPORT" in prompt
    assert "OPPOSE" in prompt
    assert len(prompt) > 200

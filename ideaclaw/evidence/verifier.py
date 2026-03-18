"""Claim-level verification — SOP gate for revision candidates.

Ported from OpenRevise scripts/check_revision_sop.py.
Classifies claims into: PASS_AUTO_REVISE | NEEDS_MANUAL_REVIEW | BLOCKED.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set


MATERIAL_CHANGE_INTENTS: Set[str] = {
    "data_metric_update",
    "threshold_update",
    "endpoint_definition_change",
    "regulatory_conclusion_update",
    "risk_language_update",
    "recommendation_grade_update",
    "definition_change",
}

RISK_TERMS: Set[str] = {"risk", "toxicity", "adverse", "safety", "warning", "严重", "风险", "毒性", "不良"}
REGULATORY_TERMS: Set[str] = {"fda", "nmpa", "ema", "approval", "approved", "认定", "批准", "监管"}
RECOMMENDATION_TERMS: Set[str] = {"grade", "level", "recommend", "优先推荐", "证据级别", "推荐级别"}


@dataclass(frozen=True)
class SourceState:
    """State of a source from the evidence gate."""
    source_id: str
    ok: bool
    detail: str
    evidence_excerpt: str


@dataclass(frozen=True)
class ClaimVerifyResult:
    """Verification result for a single claim."""
    claim_id: str
    gate_status: str  # PASS_AUTO_REVISE | NEEDS_MANUAL_REVIEW | BLOCKED
    confidence: str  # HIGH | MEDIUM | LOW
    material_gate_pass: bool
    required_sources_passed: bool
    double_check_passed: bool
    convergence: str  # consistent | conflict | unknown
    blocking_reason: str
    original_sentence: str
    proposed_revision: str
    change_intent: str
    source_refs: str
    source_locations: str
    evidence_excerpt: str
    reason: str


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _numeric_tokens(text: str) -> List[str]:
    return re.findall(r"\d+(?:\.\d+)?%?", text or "")


def _token_set(text: str) -> set:
    normalized = _normalize_text(text)
    if not normalized:
        return set()
    return set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", normalized))


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = set(a)
    set_b = set(b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def _present_terms(text: str, terms: Set[str]) -> Set[str]:
    low = _normalize_text(text)
    return {term for term in terms if term in low}


def _has_term_presence_delta(original: str, proposed: str, terms: Set[str]) -> bool:
    return _present_terms(original, terms) != _present_terms(proposed, terms)


def is_material_update(
    *,
    original_sentence: str,
    proposed_revision: str,
    change_intent: str,
) -> tuple:
    """Determine if a revision is a material (substantive) change.

    Returns (is_material: bool, reason: str).
    """
    original = _normalize_text(original_sentence)
    proposed = _normalize_text(proposed_revision)
    if not proposed:
        return False, "missing_proposed_revision"
    if original == proposed:
        return False, "cosmetic_rewrite_blocked"

    intent = (change_intent or "").strip().lower()
    similarity = _jaccard(_token_set(original_sentence), _token_set(proposed_revision))
    char_ratio = difflib.SequenceMatcher(a=original_sentence.strip(), b=proposed_revision.strip()).ratio()
    has_numeric_change = _numeric_tokens(original_sentence) != _numeric_tokens(proposed_revision)
    has_risk_delta = _has_term_presence_delta(original_sentence, proposed_revision, RISK_TERMS)
    has_regulatory_delta = _has_term_presence_delta(original_sentence, proposed_revision, REGULATORY_TERMS)
    has_recommendation_delta = _has_term_presence_delta(
        original_sentence,
        proposed_revision,
        RECOMMENDATION_TERMS,
    )
    substantive_signal = has_numeric_change or has_risk_delta or has_regulatory_delta or has_recommendation_delta

    if not substantive_signal and (similarity >= 0.9 or char_ratio >= 0.80):
        return False, "cosmetic_rewrite_blocked"

    if intent in MATERIAL_CHANGE_INTENTS:
        if substantive_signal or similarity <= 0.75 or char_ratio <= 0.70:
            return True, ""
        return False, "cosmetic_rewrite_blocked"

    if substantive_signal:
        return True, ""

    return False, "non_material_change"


def _confidence_from_claim(
    *,
    claim: Dict[str, Any],
    source_states: Dict[str, SourceState],
) -> tuple:
    """Determine confidence level from source states.

    Returns (confidence, required_pass, double_pass, convergence, reason).
    """
    required_sources = _as_list(claim.get("required_sources"))
    double_sources = _as_list(claim.get("double_check_sources"))
    source_ids = _as_list(claim.get("source_ids"))
    if not source_ids:
        source_ids = sorted(set(required_sources + double_sources))

    def source_ok(source_id: str) -> bool:
        state = source_states.get(source_id)
        return bool(state.ok) if state else False

    source_ok_map = {sid: source_ok(sid) for sid in source_ids}
    has_any_evidence = any(source_ok_map.values())
    required_pass = (
        all(source_ok(sid) for sid in required_sources) if required_sources else has_any_evidence
    )

    convergence = str(claim.get("evidence_convergence", "unknown")).strip().lower()
    if convergence not in {"consistent", "conflict", "unknown"}:
        convergence = "unknown"
    if bool(claim.get("conflict")):
        convergence = "conflict"

    double_check_pass = all(source_ok(sid) for sid in double_sources) if double_sources else False

    passed_source_count = sum(1 for sid in source_ids if source_ok(sid))
    if convergence == "conflict":
        return "LOW", required_pass, double_check_pass, convergence, "evidence_conflict_needs_manual_review"

    if required_pass and double_check_pass and passed_source_count >= 2 and convergence == "consistent":
        return "HIGH", required_pass, double_check_pass, convergence, ""

    if required_pass and has_any_evidence:
        return "MEDIUM", required_pass, double_check_pass, convergence, ""

    return "LOW", required_pass, double_check_pass, convergence, "fulltext_missing"


def _candidate_status(material_pass: bool, confidence: str) -> str:
    if not material_pass:
        return "BLOCKED"
    if confidence == "HIGH":
        return "PASS_AUTO_REVISE"
    if confidence == "MEDIUM":
        return "NEEDS_MANUAL_REVIEW"
    return "BLOCKED"


def _join_source_locations(claim: Dict[str, Any]) -> str:
    hints = _as_list(claim.get("source_locations")) or _as_list(claim.get("location_hints"))
    return ",".join(hints)


def _collect_excerpts(source_ids: Sequence[str], states: Dict[str, SourceState], limit: int = 420) -> str:
    parts: List[str] = []
    for sid in source_ids:
        state = states.get(sid)
        if not state or not state.evidence_excerpt:
            continue
        parts.append(f"[{sid}] {state.evidence_excerpt}")
    text = " | ".join(parts)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def verify_claims(
    *,
    claims: List[Dict[str, Any]],
    source_states: Dict[str, SourceState],
) -> tuple:
    """Verify all claims against source evidence.

    Returns (results: List[ClaimVerifyResult], summary: Dict).
    """
    rows: List[ClaimVerifyResult] = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id", "")).strip()
        original_sentence = str(item.get("original_sentence", "")).strip()
        proposed_revision = str(item.get("proposed_revision", "")).strip()
        change_intent = str(item.get("change_intent", "")).strip()
        reason = str(item.get("reason", "")).strip()

        material_pass, material_reason = is_material_update(
            original_sentence=original_sentence,
            proposed_revision=proposed_revision,
            change_intent=change_intent,
        )
        confidence, required_pass, double_pass, convergence, confidence_reason = _confidence_from_claim(
            claim=item,
            source_states=source_states,
        )
        gate_status = _candidate_status(material_pass, confidence)
        blocking_reason = material_reason or confidence_reason

        source_ids = _as_list(item.get("source_ids")) or sorted(
            set(_as_list(item.get("required_sources")) + _as_list(item.get("double_check_sources")))
        )
        rows.append(
            ClaimVerifyResult(
                claim_id=claim_id,
                gate_status=gate_status,
                confidence=confidence,
                material_gate_pass=material_pass,
                required_sources_passed=required_pass,
                double_check_passed=double_pass,
                convergence=convergence,
                blocking_reason=blocking_reason,
                original_sentence=original_sentence,
                proposed_revision=proposed_revision,
                change_intent=change_intent,
                source_refs=",".join(source_ids),
                source_locations=_join_source_locations(item),
                evidence_excerpt=_collect_excerpts(source_ids, source_states),
                reason=reason,
            )
        )

    auto = [r for r in rows if r.gate_status == "PASS_AUTO_REVISE"]
    manual = [r for r in rows if r.gate_status == "NEEDS_MANUAL_REVIEW"]
    blocked = [r for r in rows if r.gate_status == "BLOCKED"]
    pass_rate = (len(auto) / len(rows)) if rows else 0.0
    missing_rate = (
        len([r for r in rows if r.blocking_reason in {"fulltext_missing", "missing_proposed_revision"}]) / len(rows)
        if rows
        else 0.0
    )
    summary = {
        "claim_count": len(rows),
        "auto_revise_count": len(auto),
        "manual_review_count": len(manual),
        "blocked_count": len(blocked),
        "pass_rate": round(pass_rate, 4),
        "missing_rate": round(missing_rate, 4),
        "blocking_reason_counts": {
            reason: sum(1 for r in rows if r.blocking_reason == reason)
            for reason in sorted(set(r.blocking_reason for r in rows if r.blocking_reason))
        },
    }
    return rows, summary

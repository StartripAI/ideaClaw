"""Trust review — audits pack draft using quality profile scoring.

Bridges the quality/ system into the pipeline's Stage 14 (TRUST_REVIEW).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ideaclaw.quality.loader import load_profile, auto_detect_profile, Profile
from ideaclaw.quality.scorer import PackScorer, ScoreResult
from ideaclaw.quality.reviewer import PackReviewer, ReviewResult


@dataclass
class ClaimAudit:
    """Audit result for a single claim."""
    text: str
    status: str  # EVIDENCED | INFERRED | UNSUPPORTED | FABRICATED
    source: str = ""
    confidence: float = 0.0


@dataclass
class TrustReviewResult:
    """Result of trust review audit."""
    overall_score: float  # PQS 0-10
    verdict: str  # PASS | REVISE | FAIL
    profile_id: str = ""
    score_result: Optional[ScoreResult] = None
    review_result: Optional[ReviewResult] = None
    per_claim: List[ClaimAudit] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    required_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 2),
            "verdict": self.verdict,
            "profile_id": self.profile_id,
            "dimensions": self.score_result.to_dict()["dimensions"] if self.score_result else [],
            "review_pass_rate": self.review_result.pass_rate if self.review_result else 0,
            "per_claim": [
                {"text": c.text[:100], "status": c.status, "confidence": c.confidence}
                for c in self.per_claim
            ],
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "required_actions": self.required_actions,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class TrustReviewer:
    """Audits pack drafts for trustworthiness and evidence backing.

    Uses the quality profile system for scoring and review.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def review(
        self,
        draft: str,
        profile_id: Optional[str] = None,
        idea_text: str = "",
    ) -> TrustReviewResult:
        """Audit a pack draft for trust and evidence quality.

        Args:
            draft: The pack draft content (markdown).
            profile_id: Quality profile to use. Auto-detects if not provided.
            idea_text: Original idea text for auto-detection.

        Returns:
            TrustReviewResult with PQS score, verdict, and detailed feedback.
        """
        # Resolve profile
        pid = profile_id or self.config.get("quality", {}).get("profile_id")
        if not pid or pid == "auto":
            pid = auto_detect_profile(idea_text) if idea_text else "general.decision"

        try:
            profile = load_profile(pid)
        except FileNotFoundError:
            profile = load_profile("general.decision")
            pid = "general.decision"

        # Score with heuristic scorer
        scorer = PackScorer(profile)
        score_result = scorer.score_heuristic(draft)

        # Run structural review
        reviewer = PackReviewer(profile)
        review_result = reviewer.review(draft)

        # Audit individual claims
        per_claim = self._audit_claims(draft)

        # Derive strengths/weaknesses from scores
        strengths = []
        weaknesses = []
        for dim in score_result.dimensions:
            if dim.score >= 7.5:
                strengths.append(f"{dim.name}: {dim.feedback}")
            elif dim.score < 5.0:
                weaknesses.append(f"{dim.name}: {dim.feedback}")

        # Required actions from failed review items
        required_actions = []
        for cr in review_result.checklist_results:
            if not cr.passed:
                required_actions.append(f"Fix: {cr.item}")
        required_actions.extend(review_result.suggestions)

        return TrustReviewResult(
            overall_score=score_result.pqs,
            verdict=score_result.verdict,
            profile_id=pid,
            score_result=score_result,
            review_result=review_result,
            per_claim=per_claim,
            strengths=strengths,
            weaknesses=weaknesses,
            required_actions=required_actions[:10],
        )

    def build_llm_review_prompt(
        self,
        draft: str,
        profile_id: Optional[str] = None,
    ) -> str:
        """Build a prompt for LLM-powered trust review.

        Returns a prompt string that can be sent to an LLM for
        more accurate review than heuristic scoring.
        """
        pid = profile_id or "general.decision"
        try:
            profile = load_profile(pid)
        except FileNotFoundError:
            profile = load_profile("general.decision")

        scorer = PackScorer(profile)
        return scorer.build_llm_prompt(draft)

    def _audit_claims(self, draft: str) -> List[ClaimAudit]:
        """Extract and audit individual claims from draft."""
        import re
        claims = []

        for line in draft.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or len(line) < 30:
                continue

            if "✅" in line:
                status = "EVIDENCED"
                confidence = 0.85
            elif "⚠️" in line:
                status = "INFERRED"
                confidence = 0.5
            elif "🚫" in line:
                status = "UNSUPPORTED"
                confidence = 0.2
            else:
                # Check if line has URL or citation
                has_source = bool(re.search(r'https?://|\[source', line, re.IGNORECASE))
                status = "EVIDENCED" if has_source else "INFERRED"
                confidence = 0.7 if has_source else 0.4

            # Extract source reference if present
            source = ""
            url_match = re.search(r'(https?://\S+)', line)
            if url_match:
                source = url_match.group(1)

            claims.append(ClaimAudit(
                text=line[:200],
                status=status,
                source=source,
                confidence=confidence,
            ))

        return claims[:30]  # Cap at 30 claims

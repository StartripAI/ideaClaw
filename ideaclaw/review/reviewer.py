"""Peer review engine — ported from AI-Scientist's perform_review()."""

from __future__ import annotations
import json, logging, re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ideaclaw.review.structured import (
    NEURIPS_REVIEW_FORM, REVIEWER_SYSTEM_PROMPT_STRICT,
    REVIEWER_REFLECTION_PROMPT,
)

logger = logging.getLogger(__name__)
__all__ = ["perform_review", "ReviewResult", "PeerReviewer"]


@dataclass
class ReviewResult:
    summary: str = ""
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    originality: int = 0; quality: int = 0; clarity: int = 0; significance: int = 0
    questions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    ethical_concerns: bool = False
    soundness: int = 0; presentation: int = 0; contribution: int = 0
    overall: int = 0; confidence: int = 0; decision: str = ""
    thought: str = ""

    @classmethod
    def from_json(cls, d: Dict[str, Any]) -> "ReviewResult":
        return cls(
            summary=d.get("Summary", ""), strengths=d.get("Strengths", []),
            weaknesses=d.get("Weaknesses", []), originality=d.get("Originality", 0),
            quality=d.get("Quality", 0), clarity=d.get("Clarity", 0),
            significance=d.get("Significance", 0), questions=d.get("Questions", []),
            limitations=d.get("Limitations", []), ethical_concerns=d.get("Ethical Concerns", False),
            soundness=d.get("Soundness", 0), presentation=d.get("Presentation", 0),
            contribution=d.get("Contribution", 0), overall=d.get("Overall", 0),
            confidence=d.get("Confidence", 0), decision=d.get("Decision", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Summary": self.summary, "Strengths": self.strengths, "Weaknesses": self.weaknesses,
            "Originality": self.originality, "Quality": self.quality, "Clarity": self.clarity,
            "Significance": self.significance, "Questions": self.questions,
            "Limitations": self.limitations, "Ethical Concerns": self.ethical_concerns,
            "Soundness": self.soundness, "Presentation": self.presentation,
            "Contribution": self.contribution, "Overall": self.overall,
            "Confidence": self.confidence, "Decision": self.decision,
        }

    @property
    def is_accept(self) -> bool:
        return self.decision.lower() == "accept"

    @property
    def score_summary(self) -> str:
        return (f"Overall={self.overall}/10, Soundness={self.soundness}/4, "
                f"Originality={self.originality}/4, Clarity={self.clarity}/4, "
                f"Significance={self.significance}/4, Decision={self.decision}")


def _extract_json(text: str) -> Optional[Dict]:
    m = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    try:
        return json.loads(m.group(1)) if m else json.loads(text)
    except (json.JSONDecodeError, ValueError, AttributeError):
        return None


class PeerReviewer:
    def __init__(self, llm_call_fn: Optional[Callable] = None,
                 system_prompt: str = REVIEWER_SYSTEM_PROMPT_STRICT,
                 num_reflections: int = 5, num_ensemble: int = 1):
        self.llm_call_fn = llm_call_fn
        self.system_prompt = system_prompt
        self.num_reflections = num_reflections
        self.num_ensemble = num_ensemble

    def build_review_prompt(self, text: str) -> Dict[str, str]:
        return {
            "system": self.system_prompt,
            "user": NEURIPS_REVIEW_FORM + f"\n\nHere is the paper:\n```\n{text}\n```",
        }

    def review(self, text: str) -> ReviewResult:
        if self.llm_call_fn is None:
            raise RuntimeError("No LLM function provided.")
        if self.num_ensemble > 1:
            return self._ensemble(text)
        return self._single(text)

    def _single(self, text: str) -> ReviewResult:
        prompt = self.build_review_prompt(text)
        resp = self.llm_call_fn(prompt["system"], prompt["user"])
        rj = _extract_json(resp)
        if rj is None:
            return ReviewResult()

        # Reflection loop
        if self.num_reflections > 1:
            ctx = resp
            for j in range(1, self.num_reflections):
                ref = REVIEWER_REFLECTION_PROMPT.format(current_round=j+1, num_reflections=self.num_reflections)
                rr = self.llm_call_fn(self.system_prompt, f"Previous:\n{ctx}\n\n{ref}")
                new = _extract_json(rr)
                if new:
                    rj = new
                    ctx = rr
                if "I am done" in rr:
                    break

        return ReviewResult.from_json(rj)

    def _ensemble(self, text: str) -> ReviewResult:
        reviews = [self._single(text) for _ in range(self.num_ensemble)]
        reviews = [r for r in reviews if r.overall > 0]
        if not reviews:
            return ReviewResult()
        if len(reviews) == 1:
            return reviews[0]

        result = ReviewResult()
        for field_name, lo, hi in [("originality",1,4),("quality",1,4),("clarity",1,4),
                                    ("significance",1,4),("soundness",1,4),("presentation",1,4),
                                    ("contribution",1,4),("overall",1,10),("confidence",1,5)]:
            vals = [getattr(r, field_name) for r in reviews if lo <= getattr(r, field_name) <= hi]
            if vals:
                setattr(result, field_name, round(sum(vals)/len(vals)))

        result.strengths = list(dict.fromkeys(s for r in reviews for s in r.strengths))
        result.weaknesses = list(dict.fromkeys(w for r in reviews for w in r.weaknesses))
        result.questions = list(dict.fromkeys(q for r in reviews for q in r.questions))
        result.summary = reviews[0].summary
        result.decision = "Accept" if sum(r.is_accept for r in reviews) > len(reviews)/2 else "Reject"
        return result


def perform_review(text: str, llm_call_fn=None, num_reflections=5, num_ensemble=1, strict=True) -> ReviewResult:
    return PeerReviewer(llm_call_fn=llm_call_fn,
                        system_prompt=REVIEWER_SYSTEM_PROMPT_STRICT if strict else REVIEWER_SYSTEM_PROMPT_STRICT,
                        num_reflections=num_reflections, num_ensemble=num_ensemble).review(text)

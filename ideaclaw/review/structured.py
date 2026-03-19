"""NeurIPS review form + prompts — ported from AI-Scientist."""

from __future__ import annotations
__all__ = ["NEURIPS_REVIEW_FORM", "REVIEW_FIELDS", "REVIEWER_SYSTEM_PROMPT",
           "REVIEWER_SYSTEM_PROMPT_STRICT", "REVIEWER_REFLECTION_PROMPT", "META_REVIEWER_SYSTEM_PROMPT"]

REVIEW_FIELDS = {
    "Summary": {"type": "text"}, "Strengths": {"type": "list"}, "Weaknesses": {"type": "list"},
    "Originality": {"type": "score", "min": 1, "max": 4},
    "Quality": {"type": "score", "min": 1, "max": 4},
    "Clarity": {"type": "score", "min": 1, "max": 4},
    "Significance": {"type": "score", "min": 1, "max": 4},
    "Questions": {"type": "list"}, "Limitations": {"type": "list"},
    "Ethical Concerns": {"type": "bool"},
    "Soundness": {"type": "score", "min": 1, "max": 4},
    "Presentation": {"type": "score", "min": 1, "max": 4},
    "Contribution": {"type": "score", "min": 1, "max": 4},
    "Overall": {"type": "score", "min": 1, "max": 10},
    "Confidence": {"type": "score", "min": 1, "max": 5},
    "Decision": {"type": "enum", "values": ["Accept", "Reject"]},
}

REVIEWER_SYSTEM_PROMPT = (
    "You are an AI researcher reviewing a paper submitted to a prestigious ML venue. "
    "Be critical and cautious in your decision."
)
REVIEWER_SYSTEM_PROMPT_STRICT = REVIEWER_SYSTEM_PROMPT + " If a paper is bad or you are unsure, give it bad scores and reject it."

TEMPLATE_INSTRUCTIONS = """
Respond in the following format:
THOUGHT:
<THOUGHT>
REVIEW JSON:
```json
<JSON>
```
In <JSON>, provide: Summary, Strengths, Weaknesses, Originality(1-4), Quality(1-4),
Clarity(1-4), Significance(1-4), Questions, Limitations, Ethical Concerns(bool),
Soundness(1-4), Presentation(1-4), Contribution(1-4), Overall(1-10), Confidence(1-5),
Decision(Accept/Reject). This JSON will be automatically parsed.
"""

NEURIPS_REVIEW_FORM = """\
Review form: Summary, Strengths/Weaknesses (Originality, Quality, Clarity, Significance),
Questions, Limitations, Soundness(1-4), Presentation(1-4), Contribution(1-4),
Overall(1-10), Confidence(1-5).
""" + TEMPLATE_INSTRUCTIONS

REVIEWER_REFLECTION_PROMPT = """\
Round {current_round}/{num_reflections}. Carefully reconsider your review.
Refine scores and feedback. Same format. Include "I am done" if no changes.
"""

META_REVIEWER_SYSTEM_PROMPT = """\
You are an Area Chair. Aggregate {reviewer_count} reviews into one meta-review.
Find consensus, be critical.
"""

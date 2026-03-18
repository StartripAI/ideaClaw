"""IdeaClaw Quality Profile System.

One engine × N profiles = 122 scenarios covered.
"""

from ideaclaw.quality.loader import load_profile, auto_detect_profile, list_profiles
from ideaclaw.quality.scorer import PackScorer
from ideaclaw.quality.reviewer import PackReviewer

__all__ = [
    "load_profile",
    "auto_detect_profile",
    "list_profiles",
    "PackScorer",
    "PackReviewer",
]

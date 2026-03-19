"""User preference learning from accept/reject/edit actions.

Tracks and learns user preferences for:
  - Formatting (section structure, heading style, list style)
  - Terminology (preferred terms, domain jargon)
  - Citation style (APA, MLA, IEEE, etc.)
  - Voice and tone (formal, conversational, technical)
  - Length preferences (concise vs. detailed)

Preferences are updated incrementally from user interactions.

Usage:
    prefs = PreferenceTracker()
    prefs.record_action("accept", section="methodology", context={...})
    prefs.record_action("reject", section="introduction", reason="too verbose")
    prefs.record_action("edit", before="...", after="...", section="conclusion")

    # Later
    profile = prefs.get_profile()
    prompt_ctx = prefs.format_for_prompt()
"""

from __future__ import annotations
import logging

import json
import re
import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ['PreferenceSignal', 'UserProfile', 'PreferenceTracker']


@dataclass
class PreferenceSignal:
    """A single user preference signal from an interaction."""
    action: str                       # "accept", "reject", "edit"
    section: str = ""                 # Which section was affected
    reason: str = ""                  # Why (for rejects)
    before_text: str = ""             # Original text (for edits)
    after_text: str = ""              # User's version (for edits)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserProfile:
    """Learned user preference profile."""
    preferred_formality: float = 0.7       # 0=casual, 1=formal
    preferred_voice: str = "third_person"  # "first_person", "third_person", "passive"
    preferred_length: str = "detailed"     # "concise", "balanced", "detailed"
    preferred_citation: str = "apa"
    terminology: Dict[str, str] = field(default_factory=dict)  # term → preferred_term
    section_preferences: Dict[str, str] = field(default_factory=dict)  # section → preference note
    formatting: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0                # How confident we are in the profile

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PreferenceTracker:
    """Learns user preferences from interaction signals.

    Stores at: ~/.ideaclaw/preferences/
    """

    MIN_SIGNALS_FOR_CONFIDENCE = 5

    def __init__(self, prefs_dir: Optional[Path] = None):
        self.prefs_dir = prefs_dir or (Path.home() / ".ideaclaw" / "preferences")
        self.prefs_dir.mkdir(parents=True, exist_ok=True)
        self.signals_path = self.prefs_dir / "signals.json"
        self.profile_path = self.prefs_dir / "profile.json"
        self._signals: List[PreferenceSignal] = []
        self._profile = UserProfile()
        self._load()

    # ---- Recording ----

    def record_action(
        self,
        action: str,
        section: str = "",
        reason: str = "",
        before_text: str = "",
        after_text: str = "",
        context: Optional[Dict] = None,
    ) -> PreferenceSignal:
        """Record a user interaction signal.

        Args:
            action: "accept", "reject", or "edit".
            section: Which section was affected.
            reason: Why the user rejected (for rejects).
            before_text: Original text (for edits).
            after_text: User's edited version (for edits).
            context: Additional context.
        """
        signal = PreferenceSignal(
            action=action,
            section=section,
            reason=reason,
            before_text=before_text[:500],  # Truncate
            after_text=after_text[:500],
            context=context or {},
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        self._signals.append(signal)
        self._save_signals()

        # Re-learn profile after new signals
        if len(self._signals) % 3 == 0:  # Re-learn every 3 signals
            self._learn_profile()

        return signal

    # ---- Profile Learning ----

    def _learn_profile(self):
        """Re-learn user profile from all accumulated signals."""
        if not self._signals:
            return

        # 1. Learn formality from edits
        formality_signals = []
        for s in self._signals:
            if s.action == "edit" and s.before_text and s.after_text:
                before_formal = self._measure_formality(s.before_text)
                after_formal = self._measure_formality(s.after_text)
                formality_signals.append(after_formal)

        if formality_signals:
            self._profile.preferred_formality = sum(formality_signals) / len(formality_signals)

        # 2. Learn voice preference from edits
        voice_signals = []
        for s in self._signals:
            if s.action == "edit" and s.after_text:
                voice = self._detect_voice(s.after_text)
                voice_signals.append(voice)
        if voice_signals:
            voice_counts = Counter(voice_signals)
            self._profile.preferred_voice = voice_counts.most_common(1)[0][0]

        # 3. Learn length preference
        length_signals = []
        for s in self._signals:
            if s.action == "edit" and s.before_text and s.after_text:
                ratio = len(s.after_text) / max(len(s.before_text), 1)
                length_signals.append(ratio)
            elif s.action == "reject" and "verbose" in s.reason.lower():
                length_signals.append(0.5)
            elif s.action == "reject" and "short" in s.reason.lower():
                length_signals.append(1.5)

        if length_signals:
            avg_ratio = sum(length_signals) / len(length_signals)
            if avg_ratio < 0.8:
                self._profile.preferred_length = "concise"
            elif avg_ratio > 1.2:
                self._profile.preferred_length = "detailed"
            else:
                self._profile.preferred_length = "balanced"

        # 4. Learn terminology preferences from edits
        for s in self._signals:
            if s.action == "edit" and s.before_text and s.after_text:
                term_changes = self._detect_term_changes(s.before_text, s.after_text)
                self._profile.terminology.update(term_changes)

        # 5. Learn section preferences from rejections
        section_issues = defaultdict(list)
        for s in self._signals:
            if s.action == "reject" and s.section and s.reason:
                section_issues[s.section].append(s.reason)
        for section, reasons in section_issues.items():
            self._profile.section_preferences[section] = "; ".join(set(reasons))

        # 6. Learn citation style
        for s in self._signals:
            if s.action == "edit" and s.after_text:
                cite = self._detect_citation_style(s.after_text)
                if cite:
                    self._profile.preferred_citation = cite

        # Confidence based on number of signals
        self._profile.confidence = min(
            len(self._signals) / (self.MIN_SIGNALS_FOR_CONFIDENCE * 3),
            1.0
        )
        self._save_profile()

    def get_profile(self) -> UserProfile:
        """Get the learned user profile."""
        if self._profile.confidence < 0.2 and self._signals:
            self._learn_profile()
        return self._profile

    def format_for_prompt(self) -> str:
        """Format preferences as context for LLM prompt injection."""
        p = self.get_profile()
        if p.confidence < 0.1:
            return ""

        parts = ["## User Style Preferences\n"]

        # Core preferences
        parts.append(f"- **Formality**: {p.preferred_formality:.0%} "
                      f"({'very formal' if p.preferred_formality > 0.8 else 'formal' if p.preferred_formality > 0.6 else 'conversational'})")
        parts.append(f"- **Voice**: {p.preferred_voice.replace('_', ' ')}")
        parts.append(f"- **Length**: {p.preferred_length}")
        parts.append(f"- **Citation**: {p.preferred_citation.upper()}")

        # Terminology
        if p.terminology:
            parts.append("\n**Preferred terminology:**")
            for old, new in list(p.terminology.items())[:10]:
                parts.append(f'- Use "{new}" instead of "{old}"')

        # Section notes
        if p.section_preferences:
            parts.append("\n**Section-specific notes:**")
            for section, note in p.section_preferences.items():
                parts.append(f"- {section}: {note}")

        parts.append(f"\n*Confidence: {p.confidence:.0%} (based on {len(self._signals)} interactions)*")
        return "\n".join(parts)

    def stats(self) -> Dict[str, Any]:
        """Get preference tracking statistics."""
        by_action = Counter(s.action for s in self._signals)
        return {
            "total_signals": len(self._signals),
            "by_action": dict(by_action),
            "profile_confidence": self._profile.confidence,
            "terminology_count": len(self._profile.terminology),
        }

    # ---- Analysis Helpers ----

    @staticmethod
    def _measure_formality(text: str) -> float:
        """Estimate formality score 0-1."""
        informal_markers = [
            "i think", "you know", "kinda", "gonna", "wanna",
            "pretty much", "stuff", "things", "basically", "like ",
            "!", "...", "lol", "btw", "fyi",
        ]
        formal_markers = [
            "therefore", "furthermore", "moreover", "consequently",
            "notwithstanding", "pursuant", "herein", "thereby",
            "it is", "one may", "the authors", "this study",
        ]
        text_lower = text.lower()
        informal_count = sum(1 for m in informal_markers if m in text_lower)
        formal_count = sum(1 for m in formal_markers if m in text_lower)
        total = informal_count + formal_count
        if total == 0:
            return 0.7  # Neutral default
        return formal_count / total

    @staticmethod
    def _detect_voice(text: str) -> str:
        """Detect writing voice."""
        text_lower = text.lower()
        first_person = len(re.findall(r'\b(i|we|my|our|us)\b', text_lower))
        passive = len(re.findall(r'\b(was|were|been|being|is|are)\s+\w+ed\b', text_lower))
        third_person = len(re.findall(r'\b(the study|this paper|the authors|it is|one may)\b', text_lower))

        counts = {
            "first_person": first_person,
            "passive": passive,
            "third_person": third_person,
        }
        if max(counts.values()) == 0:
            return "third_person"
        return max(counts, key=counts.get)

    @staticmethod
    def _detect_term_changes(before: str, after: str) -> Dict[str, str]:
        """Detect terminology changes between before and after texts."""
        changes = {}
        before_words = set(before.lower().split())
        after_words = set(after.lower().split())

        removed = before_words - after_words
        added = after_words - before_words

        # Simple heuristic: if a word was removed and a similar-length word added
        for r in removed:
            if len(r) < 4:
                continue
            for a in added:
                if len(a) >= 4 and abs(len(r) - len(a)) <= 3:
                    # Could be a terminology swap
                    changes[r] = a
                    break
        return changes

    @staticmethod
    def _detect_citation_style(text: str) -> Optional[str]:
        """Detect citation style from text."""
        # APA: (Author, Year)
        if re.search(r'\([A-Z][a-z]+,?\s+\d{4}\)', text):
            return "apa"
        # MLA: (Author page)
        if re.search(r'\([A-Z][a-z]+\s+\d+\)', text):
            return "mla"
        # IEEE: [1], [2]
        if re.search(r'\[\d+\]', text):
            return "ieee"
        # Vancouver: superscript numbers
        if re.search(r'[a-z]\d+\s', text):
            return "vancouver"
        return None

    # ---- Persistence ----

    def _load(self):
        if self.signals_path.exists():
            try:
                data = json.loads(self.signals_path.read_text(encoding="utf-8"))
                self._signals = [PreferenceSignal(**d) for d in data]
            except (json.JSONDecodeError, OSError):
                self._signals = []
        if self.profile_path.exists():
            try:
                data = json.loads(self.profile_path.read_text(encoding="utf-8"))
                self._profile = UserProfile(**data)
            except (json.JSONDecodeError, OSError):
                self._profile = UserProfile()

    def _save_signals(self):
        self.signals_path.write_text(
            json.dumps([s.to_dict() for s in self._signals[-500:]], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _save_profile(self):
        self.profile_path.write_text(
            json.dumps(self._profile.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

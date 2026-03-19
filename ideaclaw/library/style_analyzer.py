"""Writing style analyzer — statistical + LLM profiling.

Statistical mode (zero dependencies):
  - TTR (Type-Token Ratio) — vocabulary richness
  - Average sentence length
  - Formality score
  - Voice ratio (active vs passive)
  - Format preferences (headings, lists, paragraphs)

LLM mode (optional):
  - Few-shot style extraction via LLM callable

Usage:
    analyzer = StyleAnalyzer()
    profile = analyzer.analyze("Your text here...")
    profile = analyzer.analyze_document(ingested_doc)
"""

from __future__ import annotations
import logging

import re
import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ['StyleProfile', 'StyleAnalyzer']


@dataclass
class StyleProfile:
    """Quantified writing style profile."""
    # Vocabulary
    ttr: float = 0.0                  # Type-Token Ratio (0-1)
    vocabulary_size: int = 0
    avg_word_length: float = 0.0

    # Sentence structure
    avg_sentence_length: float = 0.0  # Words per sentence
    sentence_length_std: float = 0.0  # Variation in sentence length
    short_sentence_pct: float = 0.0   # % sentences < 10 words
    long_sentence_pct: float = 0.0    # % sentences > 30 words

    # Formality & voice
    formality: float = 0.7            # 0=casual, 1=formal
    active_voice_pct: float = 0.5     # % active voice
    passive_voice_pct: float = 0.5    # % passive voice
    first_person_pct: float = 0.0
    third_person_pct: float = 0.0

    # Format preferences
    heading_density: float = 0.0      # Headings per 1000 words
    list_density: float = 0.0         # List items per 1000 words
    paragraph_avg_length: float = 0.0 # Words per paragraph
    uses_citations: bool = False
    citation_style: str = ""          # "apa", "ieee", "mla", etc.

    # Top terms
    top_terms: List[str] = field(default_factory=list)
    top_bigrams: List[str] = field(default_factory=list)

    # LLM-generated summary (if available)
    llm_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def format_for_prompt(self) -> str:
        """Format as context for LLM prompt injection."""
        parts = ["## Writing Style Profile\n"]
        parts.append(f"- **Vocabulary**: TTR={self.ttr:.2f}, avg word length={self.avg_word_length:.1f}")
        parts.append(f"- **Sentences**: avg {self.avg_sentence_length:.0f} words "
                      f"({self.short_sentence_pct:.0%} short, {self.long_sentence_pct:.0%} long)")

        formality_label = "very formal" if self.formality > 0.8 else \
                          "formal" if self.formality > 0.6 else \
                          "semi-formal" if self.formality > 0.4 else "conversational"
        parts.append(f"- **Formality**: {formality_label} ({self.formality:.0%})")

        voice = "active" if self.active_voice_pct > 0.6 else \
                "passive" if self.passive_voice_pct > 0.6 else "mixed"
        parts.append(f"- **Voice**: primarily {voice}")

        if self.uses_citations:
            parts.append(f"- **Citations**: {self.citation_style or 'detected'}")

        parts.append(f"- **Format**: {self.heading_density:.1f} headings/1K words, "
                      f"{self.list_density:.1f} lists/1K words")

        if self.top_terms:
            parts.append(f"- **Key terms**: {', '.join(self.top_terms[:8])}")

        if self.llm_summary:
            parts.append(f"\n**Style summary**: {self.llm_summary}")

        return "\n".join(parts)


class StyleAnalyzer:
    """Analyze writing style from text or documents."""

    # Formal markers
    FORMAL_WORDS = {
        "therefore", "furthermore", "moreover", "consequently", "nevertheless",
        "notwithstanding", "pursuant", "herein", "thereby", "whereas",
        "aforementioned", "henceforth", "respectively", "subsequently",
        "thus", "hence", "accordingly", "additionally",
    }

    INFORMAL_WORDS = {
        "gonna", "wanna", "kinda", "sorta", "gotta", "yeah", "ok",
        "awesome", "cool", "stuff", "things", "basically", "actually",
        "literally", "totally", "pretty", "super", "huge", "tons",
    }

    def analyze(self, text: str) -> StyleProfile:
        """Analyze writing style from raw text.

        Args:
            text: The text to analyze.

        Returns:
            StyleProfile with all statistical metrics.
        """
        if not text or len(text.strip()) < 50:
            return StyleProfile()

        words = re.findall(r'\b\w+\b', text.lower())
        sentences = self._split_sentences(text)

        profile = StyleProfile()

        # Vocabulary metrics
        if words:
            unique = set(words)
            profile.ttr = len(unique) / len(words) if len(words) > 0 else 0
            profile.vocabulary_size = len(unique)
            profile.avg_word_length = sum(len(w) for w in words) / len(words)

        # Sentence metrics
        if sentences:
            sent_lengths = [len(s.split()) for s in sentences]
            profile.avg_sentence_length = sum(sent_lengths) / len(sent_lengths)
            if len(sent_lengths) > 1:
                mean = profile.avg_sentence_length
                profile.sentence_length_std = (
                    sum((l - mean) ** 2 for l in sent_lengths) / len(sent_lengths)
                ) ** 0.5
            profile.short_sentence_pct = sum(1 for l in sent_lengths if l < 10) / len(sent_lengths)
            profile.long_sentence_pct = sum(1 for l in sent_lengths if l > 30) / len(sent_lengths)

        # Formality
        text_lower = text.lower()
        formal_count = sum(1 for w in self.FORMAL_WORDS if w in text_lower)
        informal_count = sum(1 for w in self.INFORMAL_WORDS if w in text_lower)
        total_markers = formal_count + informal_count
        if total_markers > 0:
            profile.formality = formal_count / total_markers
        else:
            # Heuristic: longer sentences + bigger words = more formal
            profile.formality = min(0.95, max(0.3,
                0.4 + (profile.avg_sentence_length - 10) * 0.02
                + (profile.avg_word_length - 4) * 0.1
            ))

        # Voice detection
        passive_patterns = len(re.findall(
            r'\b(?:was|were|been|being|is|are|am)\s+\w+(?:ed|en)\b', text_lower
        ))
        total_verbs = max(passive_patterns + len(re.findall(r'\b\w+(?:ed|ing|es|s)\b', text_lower)), 1)
        profile.passive_voice_pct = min(passive_patterns / total_verbs * 3, 1.0)
        profile.active_voice_pct = 1.0 - profile.passive_voice_pct

        # Person
        first = len(re.findall(r'\b(?:i|we|my|our|us|me)\b', text_lower))
        third = len(re.findall(r'\b(?:he|she|it|they|the\s+author|this\s+study)\b', text_lower))
        person_total = max(first + third, 1)
        profile.first_person_pct = first / person_total
        profile.third_person_pct = third / person_total

        # Format analysis
        word_count = len(words)
        k = max(word_count / 1000, 0.001)
        headings = len(re.findall(r'^#{1,6}\s', text, re.MULTILINE))
        headings += len(re.findall(r'\\(?:section|subsection|chapter)\{', text))
        profile.heading_density = headings / k

        list_items = len(re.findall(r'^\s*[-*•]\s', text, re.MULTILINE))
        list_items += len(re.findall(r'^\s*\d+[.)]\s', text, re.MULTILINE))
        profile.list_density = list_items / k

        paragraphs = [p for p in text.split('\n\n') if p.strip()]
        if paragraphs:
            profile.paragraph_avg_length = word_count / len(paragraphs)

        # Citations
        if re.search(r'\([A-Z]\w+,?\s+\d{4}\)', text):
            profile.uses_citations = True
            profile.citation_style = "apa"
        elif re.search(r'\[\d+\]', text):
            profile.uses_citations = True
            profile.citation_style = "ieee"
        elif re.search(r'\([A-Z]\w+\s+\d+\)', text):
            profile.uses_citations = True
            profile.citation_style = "mla"

        # Top terms (exclude stopwords)
        stopwords = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "and",
            "is", "are", "was", "were", "be", "been", "being", "have", "has",
            "had", "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "shall", "can", "this", "that", "these", "those",
            "with", "from", "by", "as", "or", "but", "not", "it", "its",
            "we", "our", "they", "their", "he", "she", "his", "her",
        }
        content_words = [w for w in words if w not in stopwords and len(w) > 2]
        term_counts = Counter(content_words)
        profile.top_terms = [w for w, _ in term_counts.most_common(15)]

        # Top bigrams
        if len(content_words) > 1:
            bigrams = [f"{content_words[i]} {content_words[i+1]}"
                      for i in range(len(content_words) - 1)]
            bigram_counts = Counter(bigrams)
            profile.top_bigrams = [b for b, c in bigram_counts.most_common(10) if c > 1]

        return profile

    def analyze_with_llm(
        self,
        text: str,
        llm_callable: Callable[[str], str],
    ) -> str:
        """Get LLM-generated style summary to complement statistical analysis.

        Returns a 2-3 sentence style description.
        """
        prompt = f"""Analyze the writing style of this text in 2-3 sentences.
Cover: tone, formality, vocabulary level, sentence patterns, and any distinctive features.

Text (first 2000 chars):
{text[:2000]}

Style analysis:"""

        try:
            return llm_callable(prompt).strip()
        except Exception:  # noqa: BLE001
            return ""

    def analyze_document(self, doc) -> StyleProfile:
        """Analyze an IngestedDocument's style."""
        if hasattr(doc, "full_text") and doc.full_text:
            return self.analyze(doc.full_text)
        if hasattr(doc, "chunks") and doc.chunks:
            all_text = " ".join(c.text for c in doc.chunks)
            return self.analyze(all_text)
        return StyleProfile()

    def merge_profiles(self, profiles: List[StyleProfile]) -> StyleProfile:
        """Merge multiple style profiles into an average."""
        if not profiles:
            return StyleProfile()
        if len(profiles) == 1:
            return profiles[0]

        n = len(profiles)
        merged = StyleProfile()

        # Average numeric fields
        for field_name in [
            "ttr", "avg_word_length", "avg_sentence_length", "sentence_length_std",
            "short_sentence_pct", "long_sentence_pct", "formality",
            "active_voice_pct", "passive_voice_pct", "first_person_pct",
            "third_person_pct", "heading_density", "list_density", "paragraph_avg_length",
        ]:
            values = [getattr(p, field_name) for p in profiles]
            setattr(merged, field_name, sum(values) / n)

        # Sum vocabulary
        merged.vocabulary_size = max(p.vocabulary_size for p in profiles)

        # Most common citation style
        cite_styles = [p.citation_style for p in profiles if p.citation_style]
        if cite_styles:
            merged.citation_style = Counter(cite_styles).most_common(1)[0][0]
            merged.uses_citations = True

        # Merge top terms
        all_terms = []
        for p in profiles:
            all_terms.extend(p.top_terms)
        term_counts = Counter(all_terms)
        merged.top_terms = [t for t, _ in term_counts.most_common(15)]

        return merged

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split text into sentences."""
        # Handle common abbreviations
        text = re.sub(r'(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e)\.', r'\1<DOT>', text)
        sentences = re.split(r'[.!?]+\s+', text)
        sentences = [s.replace('<DOT>', '.').strip() for s in sentences if s.strip()]
        return sentences

"""Universal Pack Reviewer — checklist-based review using profile standards.

Performs automated structure and content checks without requiring an LLM.
For LLM-powered review, use PackScorer.build_llm_prompt() instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ideaclaw.quality.loader import Profile


@dataclass
class CheckResult:
    item: str
    passed: bool
    detail: str = ""


@dataclass
class ReviewResult:
    """Complete review result."""
    profile_id: str
    passed: int
    failed: int
    total: int
    checklist_results: List[CheckResult] = field(default_factory=list)
    structure_issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "pass_rate": round(self.pass_rate, 2),
            "checklist_results": [
                {"item": c.item, "passed": c.passed, "detail": c.detail}
                for c in self.checklist_results
            ],
            "structure_issues": self.structure_issues,
            "suggestions": self.suggestions,
        }


class PackReviewer:
    """Reviews a pack against a profile's format and checklist requirements."""

    def __init__(self, profile: Profile):
        self.profile = profile

    def review(self, pack_content: str) -> ReviewResult:
        """Run all review checks against the pack content."""
        results = []
        structure_issues = []
        suggestions = []

        # 1. Check required sections
        section_results = self._check_sections(pack_content)
        results.extend(section_results)

        # 2. Check format constraints
        constraint_results, c_issues = self._check_constraints(pack_content)
        results.extend(constraint_results)
        structure_issues.extend(c_issues)

        # 3. Check profile-specific checklist items
        checklist_results = self._check_checklist(pack_content)
        results.extend(checklist_results)

        # 4. Check source requirements
        source_results, s_suggestions = self._check_sources(pack_content)
        results.extend(source_results)
        suggestions.extend(s_suggestions)

        # 5. General quality checks
        quality_results, q_suggestions = self._check_quality(pack_content)
        results.extend(quality_results)
        suggestions.extend(q_suggestions)

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return ReviewResult(
            profile_id=self.profile.id,
            passed=passed,
            failed=failed,
            total=len(results),
            checklist_results=results,
            structure_issues=structure_issues,
            suggestions=suggestions,
        )

    def _check_sections(self, content: str) -> List[CheckResult]:
        """Check that required sections are present."""
        results = []
        content_lower = content.lower()

        for section in self.profile.sections:
            name = section.get("name", "")
            required = section.get("required", False)
            if not name:
                continue

            # Look for section header
            variants = [name, name.replace("_", " "), name.title(), name.upper()]
            found = any(v.lower() in content_lower for v in variants)

            results.append(CheckResult(
                item=f"Section '{name}' present",
                passed=found or not required,
                detail="" if found else ("REQUIRED but missing" if required else "Optional, not found"),
            ))

            # Check min_count if specified (e.g., references min_count: 15)
            min_count = section.get("min_count")
            if min_count and found:
                # Count items in section (rough estimate by counting list items after header)
                pattern = re.compile(
                    rf'(?:^|\n)#+\s*{re.escape(name)}.*?\n(.*?)(?=\n#+\s|\Z)',
                    re.IGNORECASE | re.DOTALL
                )
                match = pattern.search(content)
                if match:
                    section_text = match.group(1)
                    item_count = len(re.findall(r'^\s*[\d\-\*]\s', section_text, re.MULTILINE))
                    results.append(CheckResult(
                        item=f"Section '{name}' has ≥{min_count} items",
                        passed=item_count >= min_count,
                        detail=f"Found {item_count} items" if item_count < min_count else "",
                    ))

        return results

    def _check_constraints(self, content: str) -> tuple:
        """Check format constraints like max_words, citation_style, etc."""
        results = []
        issues = []
        constraints = self.profile.constraints

        if not constraints:
            return results, issues

        # Max words
        max_words = constraints.get("max_words")
        if max_words:
            word_count = len(content.split())
            passed = word_count <= max_words
            results.append(CheckResult(
                item=f"Word count ≤ {max_words}",
                passed=passed,
                detail=f"Actual: {word_count}" if not passed else "",
            ))
            if not passed:
                issues.append(f"Exceeds word limit: {word_count}/{max_words}")

        # Max pages (approx 300 words per page)
        max_pages = constraints.get("max_pages")
        if max_pages:
            word_count = len(content.split())
            estimated_pages = word_count / 300
            passed = estimated_pages <= max_pages + 0.5
            results.append(CheckResult(
                item=f"Page count ≤ {max_pages}",
                passed=passed,
                detail=f"Estimated: {estimated_pages:.1f} pages" if not passed else "",
            ))

        # Citation style check
        citation_style = constraints.get("citation_style")
        if citation_style:
            style_ok = self._check_citation_style(content, citation_style)
            results.append(CheckResult(
                item=f"Citation style: {citation_style}",
                passed=style_ok,
                detail="" if style_ok else f"Expected {citation_style} style citations",
            ))

        # Language check
        language = constraints.get("language")
        if language == "en":
            # Simple check: mostly ASCII
            ascii_ratio = sum(1 for c in content if ord(c) < 128) / max(len(content), 1)
            results.append(CheckResult(
                item="Language: English",
                passed=ascii_ratio > 0.8,
            ))

        return results, issues

    def _check_citation_style(self, content: str, style: str) -> bool:
        """Check if citations match expected style."""
        if style == "author-year":
            return bool(re.search(r'\([A-Z][a-z]+.*?\d{4}\)', content))
        elif style == "numbered":
            return bool(re.search(r'\[\d+\]', content))
        elif style in ("vancouver", "apa", "mla"):
            # Loose check for any structured references
            return bool(re.search(r'(?:references|bibliography|sources)', content, re.IGNORECASE))
        return True  # Unknown style, pass

    def _check_checklist(self, content: str) -> List[CheckResult]:
        """Check profile-specific checklist items using keyword matching."""
        results = []
        content_lower = content.lower()

        for item in self.profile.checklist:
            # Extract key concepts from the checklist item
            key_terms = re.findall(r'\b\w{4,}\b', item.lower())
            # Consider passed if ≥ 50% of key terms appear in content
            matches = sum(1 for t in key_terms if t in content_lower)
            threshold = max(1, len(key_terms) // 2)
            passed = matches >= threshold

            results.append(CheckResult(
                item=item,
                passed=passed,
                detail="" if passed else "Not detected in content",
            ))

        return results

    def _check_sources(self, content: str) -> tuple:
        """Check source requirements."""
        results = []
        suggestions = []
        src_req = self.profile.source_requirements

        if not src_req:
            return results, suggestions

        # Min sources
        min_sources = src_req.get("min_sources")
        if min_sources:
            urls = len(re.findall(r'https?://', content))
            citations = len(re.findall(r'\[(?:Source|Ref|\d)', content))
            total = max(urls, citations)
            passed = total >= min_sources
            results.append(CheckResult(
                item=f"≥{min_sources} sources cited",
                passed=passed,
                detail=f"Found ~{total}" if not passed else "",
            ))

        # Preferred databases
        preferred = src_req.get("preferred_databases", [])
        if preferred:
            content_lower = content.lower()
            found_dbs = [db for db in preferred if db.lower().replace("_", " ") in content_lower]
            if not found_dbs:
                suggestions.append(f"Consider citing sources from: {', '.join(preferred)}")

        return results, suggestions

    def _check_quality(self, content: str) -> tuple:
        """General quality checks applicable to all profiles."""
        results = []
        suggestions = []

        # Check for evidence markers
        has_evidence_markers = bool(re.search(r'[✅⚠️🚫]', content))
        results.append(CheckResult(
            item="Evidence markers (✅⚠️🚫) present",
            passed=has_evidence_markers,
            detail="" if has_evidence_markers else "Add ✅ ⚠️ 🚫 markers to claims",
        ))

        # Check for conclusion/summary at the top
        first_500 = content[:500].lower()
        has_summary = any(w in first_500 for w in [
            "conclusion", "summary", "executive summary", "bottom line",
            "recommendation", "verdict", "overview",
        ])
        results.append(CheckResult(
            item="Conclusion/summary near the top",
            passed=has_summary,
        ))

        # Check for sources section
        has_sources = bool(re.search(r'(?:^|\n)#+\s*(?:sources|references|bibliography)',
                                     content, re.IGNORECASE))
        results.append(CheckResult(
            item="Sources section present",
            passed=has_sources,
        ))

        # Suggest improvements
        word_count = len(content.split())
        if word_count < 200:
            suggestions.append("Pack is very short — consider expanding with more detail")
        if not re.search(r'action|next step|recommend', content, re.IGNORECASE):
            suggestions.append("Consider adding action items or next steps")

        return results, suggestions

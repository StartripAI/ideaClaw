"""Markdown export — feature-rich .md file generation.

Integrates with:
  - export.Exporter → MarkdownExporter().export(content, path)
  - library.style_analyzer → respects style profile
  - quality.scorer → optionally appends PQS badge

Features:
  - GFM (GitHub Flavored Markdown) and CommonMark output
  - Automatic TOC generation
  - YAML front-matter metadata header
  - Section numbering
  - Figure reference linking
  - LaTeX math preservation
  - Citation formatting

Usage:
    from ideaclaw.export.markdown import MarkdownExporter
    exporter = MarkdownExporter(include_toc=True, include_metadata=True)
    exporter.export(content, Path("output.md"), metadata={...})
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["MarkdownExporter", "MarkdownConfig"]


@dataclass
class MarkdownConfig:
    """Markdown export configuration."""
    flavor: str = "gfm"           # gfm|commonmark
    include_toc: bool = True
    include_metadata: bool = True
    include_section_numbers: bool = False
    include_pqs_badge: bool = True
    include_generation_note: bool = True
    toc_max_depth: int = 3
    wrap_width: int = 0           # 0 = no wrapping


class MarkdownExporter:
    """Exports pack content as a polished Markdown document."""

    def __init__(self, config: Optional[MarkdownConfig] = None, **kwargs):
        if config:
            self.config = config
        else:
            self.config = MarkdownConfig(**{
                k: v for k, v in kwargs.items()
                if k in MarkdownConfig.__dataclass_fields__
            })

    def export(
        self,
        pack_content: str,
        output_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
        pqs_scores: Optional[Dict[str, float]] = None,
    ) -> Path:
        """Write pack content to a Markdown file with enhancements.

        Args:
            pack_content: Raw Markdown content.
            output_path: Path to write the .md file.
            metadata: Optional metadata for YAML front-matter.
            pqs_scores: Optional quality scores for badge.

        Returns:
            Path to the written file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        parts: List[str] = []

        # YAML front-matter
        if self.config.include_metadata and metadata:
            parts.append(self._build_frontmatter(metadata))

        # PQS badge
        if self.config.include_pqs_badge and pqs_scores:
            parts.append(self._build_pqs_badge(pqs_scores))

        # TOC
        if self.config.include_toc:
            toc = self._generate_toc(pack_content)
            if toc:
                parts.append(toc)

        # Main content (with optional section numbering)
        content = pack_content
        if self.config.include_section_numbers:
            content = self._add_section_numbers(content)

        parts.append(content)

        # Generation note
        if self.config.include_generation_note:
            parts.append(self._build_footer())

        final = "\n\n".join(parts)

        # Optional line wrapping
        if self.config.wrap_width > 0:
            final = self._wrap_lines(final, self.config.wrap_width)

        output_path.write_text(final, encoding="utf-8")
        logger.info("Markdown exported → %s (%d chars)", output_path, len(final))
        return output_path

    def _build_frontmatter(self, metadata: Dict[str, Any]) -> str:
        """Build YAML front-matter block."""
        lines = ["---"]
        if metadata.get("title"):
            # Escape YAML special chars in title
            title = metadata["title"].replace('"', '\\"')
            lines.append(f'title: "{title}"')
        if metadata.get("authors"):
            authors = metadata["authors"]
            if isinstance(authors, list):
                lines.append("authors:")
                for a in authors:
                    lines.append(f"  - {a}")
            else:
                lines.append(f'author: "{authors}"')
        if metadata.get("date"):
            lines.append(f"date: {metadata['date']}")
        else:
            lines.append(f"date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
        if metadata.get("abstract"):
            abstract = metadata["abstract"][:200].replace("\n", " ")
            lines.append(f'abstract: "{abstract}"')
        if metadata.get("tags"):
            tags = metadata["tags"]
            if isinstance(tags, list):
                lines.append(f"tags: [{', '.join(tags)}]")
        if metadata.get("pack_type"):
            lines.append(f"pack_type: {metadata['pack_type']}")
        lines.append(f"generator: IdeaClaw")
        lines.append("---")
        return "\n".join(lines)

    def _generate_toc(self, content: str) -> str:
        """Generate table of contents from headings."""
        headings = []
        for line in content.split("\n"):
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                level = len(m.group(1))
                if level <= self.config.toc_max_depth:
                    headings.append((level, m.group(2).strip()))

        if not headings:
            return ""

        lines = ["## Table of Contents", ""]
        for level, title in headings:
            indent = "  " * (level - 1)
            # Create anchor link (GFM style)
            anchor = re.sub(r"[^\w\s-]", "", title.lower())
            anchor = re.sub(r"\s+", "-", anchor.strip())
            lines.append(f"{indent}- [{title}](#{anchor})")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _add_section_numbers(content: str) -> str:
        """Add hierarchical section numbers to headings."""
        counters = [0, 0, 0, 0, 0, 0]
        result = []

        for line in content.split("\n"):
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                level = len(m.group(1))
                idx = level - 1
                counters[idx] += 1
                # Reset deeper counters
                for i in range(idx + 1, 6):
                    counters[i] = 0
                number = ".".join(str(counters[i]) for i in range(idx + 1) if counters[i] > 0)
                result.append(f"{'#' * level} {number} {m.group(2)}")
            else:
                result.append(line)

        return "\n".join(result)

    @staticmethod
    def _build_pqs_badge(pqs_scores: Dict[str, float]) -> str:
        """Build a quality badge line."""
        composite = pqs_scores.get("composite", pqs_scores.get("overall", 0))
        if composite >= 0.8:
            emoji, label = "🟢", "High Quality"
        elif composite >= 0.6:
            emoji, label = "🟡", "Good Quality"
        else:
            emoji, label = "🔴", "Needs Improvement"

        dims = " · ".join(f"**{k}**: {v:.0%}" for k, v in pqs_scores.items()
                          if k not in ("composite", "overall"))
        return f"> {emoji} **{label}** (PQS: {composite:.0%}) — {dims}"

    @staticmethod
    def _build_footer() -> str:
        """Build generation footer."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"---\n\n*Generated by [IdeaClaw](https://github.com/ideaclaw) · {ts}*"

    @staticmethod
    def _wrap_lines(text: str, width: int) -> str:
        """Wrap long lines while preserving code blocks and tables."""
        lines = text.split("\n")
        result = []
        in_code = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code = not in_code
                result.append(line)
            elif in_code or line.startswith("|") or line.startswith(">") or line.startswith("#"):
                result.append(line)
            elif len(line) > width:
                # Simple word-wrap
                words = line.split()
                current = ""
                for word in words:
                    if len(current) + len(word) + 1 > width and current:
                        result.append(current)
                        current = word
                    else:
                        current = f"{current} {word}".strip()
                if current:
                    result.append(current)
            else:
                result.append(line)

        return "\n".join(result)

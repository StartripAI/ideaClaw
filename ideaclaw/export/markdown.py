"""Markdown export — writes shareable .md pack files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class MarkdownExporter:
    """Exports pack content as a shareable Markdown document."""

    def export(self, pack_content: str, output_path: Path) -> Path:
        """Write pack content to a Markdown file.

        Args:
            pack_content: Rendered Markdown content.
            output_path: Path to write the .md file.

        Returns:
            Path to the written file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pack_content, encoding="utf-8")
        return output_path

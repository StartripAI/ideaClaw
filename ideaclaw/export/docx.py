"""DOCX export — converts markdown pack content to .docx format.

Uses python-docx if available, otherwise falls back to plain text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict


class DocxExporter:
    """Exports pack content as a DOCX document.

    Converts markdown to DOCX using python-docx if available.
    Falls back to plain text .docx-shaped output otherwise.
    """

    def export(self, pack_content: str, output_path: Path) -> Path:
        """Write pack content to a DOCX file.

        Args:
            pack_content: Rendered Markdown content.
            output_path: Path to write the .docx file.

        Returns:
            Path to the written file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            return self._export_with_python_docx(pack_content, output_path)
        except ImportError:
            # Fallback: write markdown as plain text with .docx extension
            output_path.write_text(pack_content, encoding="utf-8")
            return output_path

    def _export_with_python_docx(self, content: str, path: Path) -> Path:
        """Export using python-docx library."""
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # Set default font
        style = doc.styles["Normal"]
        font = style.font
        font.size = Pt(11)
        font.name = "Calibri"

        for line in content.split("\n"):
            stripped = line.strip()

            if not stripped:
                doc.add_paragraph("")
                continue

            # Headers
            if stripped.startswith("# "):
                p = doc.add_heading(self._clean_md(stripped[2:]), level=1)
            elif stripped.startswith("## "):
                p = doc.add_heading(self._clean_md(stripped[3:]), level=2)
            elif stripped.startswith("### "):
                p = doc.add_heading(self._clean_md(stripped[4:]), level=3)
            # Horizontal rule
            elif stripped.startswith("---"):
                doc.add_paragraph("─" * 40)
            # Blockquote
            elif stripped.startswith("> "):
                p = doc.add_paragraph(self._clean_md(stripped[2:]))
                p.style = doc.styles["Quote"] if "Quote" in doc.styles else doc.styles["Normal"]
            # List items
            elif stripped.startswith("- ") or stripped.startswith("* "):
                doc.add_paragraph(self._clean_md(stripped[2:]), style="List Bullet")
            elif re.match(r"^\d+\.\s", stripped):
                text = re.sub(r"^\d+\.\s", "", stripped)
                doc.add_paragraph(self._clean_md(text), style="List Number")
            # Table (skip markdown table syntax)
            elif stripped.startswith("|"):
                # Simple table row — render as text
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                if cells and not all(c.startswith("-") for c in cells):
                    doc.add_paragraph("  |  ".join(cells))
            # Italic/emphasis
            elif stripped.startswith("*") and stripped.endswith("*"):
                p = doc.add_paragraph()
                run = p.add_run(stripped.strip("*_"))
                run.italic = True
            # Normal paragraph
            else:
                doc.add_paragraph(self._clean_md(stripped))

        doc.save(str(path))
        return path

    def _clean_md(self, text: str) -> str:
        """Remove markdown formatting from text."""
        # Remove bold
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        # Remove italic
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        # Remove inline code
        text = re.sub(r"`(.*?)`", r"\1", text)
        # Remove links — keep text
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
        # Remove emoji (keep for readability)
        return text

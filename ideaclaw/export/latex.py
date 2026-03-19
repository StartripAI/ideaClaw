"""LaTeX export — generates conference-ready LaTeX papers.

Supports NeurIPS, ICML, ICLR, and generic academic templates.
Converts pack content (markdown) to LaTeX with proper formatting.
"""

from __future__ import annotations
import logging

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["NEURIPS_PREAMBLE", "ICML_PREAMBLE", "ICLR_PREAMBLE", "GENERIC_PREAMBLE", "TEMPLATE_MAP", "LaTeXExporter"]


# ---------------------------------------------------------------------------
# LaTeX templates (preambles)
# ---------------------------------------------------------------------------

NEURIPS_PREAMBLE = r"""\documentclass{article}
\usepackage[final]{neurips_2024}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{amsfonts}
\usepackage{nicefrac}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{natbib}
"""

ICML_PREAMBLE = r"""\documentclass[accepted]{icml2024}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{amsfonts}
\usepackage{nicefrac}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{natbib}
"""

ICLR_PREAMBLE = r"""\documentclass{article}
\usepackage{iclr2025_conference}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{amsfonts}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{natbib}
"""

GENERIC_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{amsfonts}
\usepackage{amsmath}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{natbib}
\usepackage{xcolor}
"""

TEMPLATE_MAP = {
    "neurips": NEURIPS_PREAMBLE,
    "icml": ICML_PREAMBLE,
    "iclr": ICLR_PREAMBLE,
    "generic": GENERIC_PREAMBLE,
}


class LaTeXExporter:
    """Exports pack content as a LaTeX document.

    Converts markdown content to LaTeX with:
    - Conference template selection (NeurIPS/ICML/ICLR/generic)
    - Heading conversion (# → \\section, ## → \\subsection, etc.)
    - List conversion (- → \\begin{itemize})
    - Table conversion (| → \\begin{tabular})
    - Bold/italic/code conversion
    - Citation formatting
    - BibTeX generation from sources
    """

    def __init__(self, template: str = "generic"):
        self.template = template.lower()
        self.preamble = TEMPLATE_MAP.get(self.template, GENERIC_PREAMBLE)

    def export(
        self,
        pack_content: str,
        output_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
        sources: Optional[List[Dict[str, str]]] = None,
    ) -> Path:
        """Convert markdown pack to LaTeX and write to file.

        Args:
            pack_content: Rendered markdown content.
            output_path: Path to write the .tex file.
            metadata: Optional dict with 'title', 'authors', 'abstract', etc.
            sources: Optional list of source dicts for BibTeX.

        Returns:
            Path to the written .tex file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = metadata or {}
        sources = sources or []

        latex = self._build_document(pack_content, metadata, sources)
        output_path.write_text(latex, encoding="utf-8")

        # Write BibTeX file alongside
        if sources:
            bib_path = output_path.with_suffix(".bib")
            bib_content = self._generate_bibtex(sources)
            bib_path.write_text(bib_content, encoding="utf-8")

        return output_path

    def _build_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        sources: List[Dict[str, str]],
    ) -> str:
        """Build full LaTeX document from markdown content."""
        parts = [self.preamble]

        # Title
        title = metadata.get("title", "IdeaClaw Pack")
        parts.append(f"\\title{{{self._escape(title)}}}")

        # Authors
        authors = metadata.get("authors", ["IdeaClaw"])
        if isinstance(authors, list):
            author_str = " \\and ".join(self._escape(a) for a in authors)
        else:
            author_str = self._escape(str(authors))
        parts.append(f"\\author{{{author_str}}}")

        parts.append("\\begin{document}")
        parts.append("\\maketitle")

        # Abstract
        abstract = metadata.get("abstract", "")
        if abstract:
            parts.append("\\begin{abstract}")
            parts.append(self._escape(abstract))
            parts.append("\\end{abstract}")

        # Convert markdown body to LaTeX
        body = self._md_to_latex(content)
        parts.append(body)

        # Bibliography
        if sources:
            bib_name = "references"
            parts.append("")
            parts.append("\\bibliographystyle{plainnat}")
            parts.append(f"\\bibliography{{{bib_name}}}")

        parts.append("\\end{document}")
        return "\n\n".join(parts)

    def _md_to_latex(self, content: str) -> str:
        """Convert markdown to LaTeX body content."""
        lines = content.split("\n")
        output_lines: List[str] = []
        in_list = False
        in_table = False
        table_buffer: List[str] = []

        for line in lines:
            stripped = line.strip()

            # Empty line
            if not stripped:
                if in_list:
                    output_lines.append("\\end{itemize}")
                    in_list = False
                if in_table:
                    output_lines.append(self._render_table(table_buffer))
                    table_buffer = []
                    in_table = False
                output_lines.append("")
                continue

            # Headers
            if stripped.startswith("#### "):
                if in_list:
                    output_lines.append("\\end{itemize}")
                    in_list = False
                output_lines.append(f"\\paragraph{{{self._escape(self._strip_md(stripped[5:]))}}}")
                continue
            if stripped.startswith("### "):
                if in_list:
                    output_lines.append("\\end{itemize}")
                    in_list = False
                output_lines.append(f"\\subsubsection{{{self._escape(self._strip_md(stripped[4:]))}}}")
                continue
            if stripped.startswith("## "):
                if in_list:
                    output_lines.append("\\end{itemize}")
                    in_list = False
                output_lines.append(f"\\subsection{{{self._escape(self._strip_md(stripped[3:]))}}}")
                continue
            if stripped.startswith("# "):
                if in_list:
                    output_lines.append("\\end{itemize}")
                    in_list = False
                output_lines.append(f"\\section{{{self._escape(self._strip_md(stripped[2:]))}}}")
                continue

            # Horizontal rule
            if stripped.startswith("---"):
                output_lines.append("\\vspace{1em}\\hrule\\vspace{1em}")
                continue

            # List items
            if stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    output_lines.append("\\begin{itemize}")
                    in_list = True
                item_text = self._convert_inline(stripped[2:])
                output_lines.append(f"  \\item {item_text}")
                continue

            # Numbered list
            if re.match(r"^\d+\.\s", stripped):
                text = re.sub(r"^\d+\.\s", "", stripped)
                if not in_list:
                    output_lines.append("\\begin{itemize}")
                    in_list = True
                output_lines.append(f"  \\item {self._convert_inline(text)}")
                continue

            # Table
            if stripped.startswith("|"):
                in_table = True
                table_buffer.append(stripped)
                continue

            # Blockquote
            if stripped.startswith("> "):
                text = self._convert_inline(stripped[2:])
                output_lines.append(f"\\begin{{quote}}\n{text}\n\\end{{quote}}")
                continue

            # Normal paragraph
            if in_list:
                output_lines.append("\\end{itemize}")
                in_list = False
            output_lines.append(self._convert_inline(stripped))

        if in_list:
            output_lines.append("\\end{itemize}")
        if in_table:
            output_lines.append(self._render_table(table_buffer))

        return "\n".join(output_lines)

    def _render_table(self, rows: List[str]) -> str:
        """Convert markdown table rows to LaTeX tabular."""
        if not rows:
            return ""

        # Parse cells
        parsed = []
        for row in rows:
            cells = [c.strip() for c in row.split("|")[1:-1]]
            if cells and not all(c.startswith("-") for c in cells):
                parsed.append(cells)

        if not parsed:
            return ""

        ncols = max(len(r) for r in parsed)
        col_spec = "|" + "l|" * ncols

        lines = [f"\\begin{{tabular}}{{{col_spec}}}"]
        lines.append("\\hline")

        for i, row_cells in enumerate(parsed):
            # Pad if needed
            while len(row_cells) < ncols:
                row_cells.append("")
            escaped = [self._escape(self._strip_md(c)) for c in row_cells]
            lines.append(" & ".join(escaped) + " \\\\")
            if i == 0:
                lines.append("\\hline")

        lines.append("\\hline")
        lines.append("\\end{tabular}")
        return "\n".join(lines)

    def _convert_inline(self, text: str) -> str:
        """Convert inline markdown (bold, italic, code, links) to LaTeX."""
        text = self._escape(text)
        # Bold: **text** → \textbf{text}
        text = re.sub(r"\*\*(.*?)\*\*", r"\\textbf{\1}", text)
        # Italic: *text* → \textit{text}
        text = re.sub(r"\*(.*?)\*", r"\\textit{\1}", text)
        # Inline code: `text` → \texttt{text}
        text = re.sub(r"`(.*?)`", r"\\texttt{\1}", text)
        # Links: [text](url) → \href{url}{text}
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\\href{\2}{\1}", text)
        return text

    def _escape(self, text: str) -> str:
        """Escape LaTeX special characters."""
        # Order matters: & must come before items that might produce &
        chars = {
            "\\": "\\textbackslash{}",
            "&": "\\&",
            "%": "\\%",
            "$": "\\$",
            "#": "\\#",
            "_": "\\_",
            "{": "\\{",
            "}": "\\}",
            "~": "\\textasciitilde{}",
            "^": "\\textasciicircum{}",
        }
        for char, replacement in chars.items():
            text = text.replace(char, replacement)
        return text

    def _strip_md(self, text: str) -> str:
        """Remove markdown formatting from text."""
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"`(.*?)`", r"\1", text)
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
        # Remove emoji
        text = re.sub(r"[✅⚠️🚫❓📌📦🦞🔬🧠📝]", "", text)
        return text.strip()

    def _generate_bibtex(self, sources: List[Dict[str, str]]) -> str:
        """Generate BibTeX entries from source list."""
        entries = []
        for i, src in enumerate(sources):
            key = f"source{i + 1}"
            title = src.get("title", "Unknown")
            url = src.get("url", "")
            doi = src.get("doi", "")
            authors = src.get("authors", "Unknown")
            year = src.get("year", "2024")

            if isinstance(authors, list):
                authors = " and ".join(authors)

            entry_lines = [
                f"@article{{{key},",
                f"  title = {{{title}}},",
                f"  author = {{{authors}}},",
                f"  year = {{{year}}},",
            ]
            if url:
                entry_lines.append(f"  url = {{{url}}},")
            if doi:
                entry_lines.append(f"  doi = {{{doi}}},")
            entry_lines.append("}")
            entries.append("\n".join(entry_lines))

        return "\n\n".join(entries)

"""LaTeX Style Registry — automatic style selection based on profile.

Maps scenario profiles to their LaTeX style files.
Provides fallback to a default academic style.

Usage:
    from ideaclaw.export.styles import get_style_for_profile, list_available_styles

    style = get_style_for_profile("icml_2025")
    print(style.sty_path, style.bst_path)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


STYLES_DIR = Path(__file__).parent


@dataclass
class LaTeXStyle:
    """A LaTeX style configuration."""
    name: str
    sty_file: str
    bst_file: str = "plainnat.bst"  # Default BibTeX style
    description: str = ""
    document_class: str = "article"
    options: str = ""

    @property
    def sty_path(self) -> Optional[Path]:
        """Get full path to .sty file if it exists."""
        path = STYLES_DIR / self.name / self.sty_file
        return path if path.exists() else None

    @property
    def bst_path(self) -> Optional[Path]:
        """Get full path to .bst file if it exists."""
        path = STYLES_DIR / "bibtex" / self.bst_file
        if path.exists():
            return path
        # Try in style-specific directory
        path = STYLES_DIR / self.name / self.bst_file
        return path if path.exists() else None


# ---------------------------------------------------------------------------
# Style Registry
# ---------------------------------------------------------------------------

STYLE_REGISTRY: Dict[str, LaTeXStyle] = {
    "icml_2025": LaTeXStyle(
        name="icml_2025",
        sty_file="icml2025.sty",
        bst_file="plainnat.bst",
        description="ICML 2025 conference style",
        document_class="article",
        options="accepted",
    ),
    "neurips_2025": LaTeXStyle(
        name="neurips_2025",
        sty_file="neurips_2025.sty",
        bst_file="plainnat.bst",
        description="NeurIPS 2025 conference style",
        document_class="article",
    ),
    "iclr_2026": LaTeXStyle(
        name="iclr_2026",
        sty_file="iclr2026_conference.sty",
        bst_file="plainnat.bst",
        description="ICLR 2026 conference style",
        document_class="article",
    ),
    "aaai_2025": LaTeXStyle(
        name="aaai_2025",
        sty_file="aaai25.sty",
        bst_file="aaai.bst",
        description="AAAI 2025 conference style",
        document_class="article",
    ),
    "acl_2025": LaTeXStyle(
        name="acl_2025",
        sty_file="acl2025.sty",
        bst_file="acl_natbib.bst",
        description="ACL 2025 conference style",
        document_class="article",
    ),
    "ieee": LaTeXStyle(
        name="ieee",
        sty_file="IEEEtran.cls",
        bst_file="IEEEtran.bst",
        description="IEEE Transactions style",
        document_class="IEEEtran",
        options="journal",
    ),
    "nature": LaTeXStyle(
        name="nature",
        sty_file="nature.sty",
        bst_file="naturemag.bst",
        description="Nature journal style",
        document_class="article",
    ),
    "default": LaTeXStyle(
        name="default",
        sty_file="article.sty",
        bst_file="plainnat.bst",
        description="Default academic article",
        document_class="article",
        options="12pt,a4paper",
    ),
}

# Profile ID → style key mapping (for fuzzy matching)
PROFILE_STYLE_MAP: Dict[str, str] = {
    "icml_2025": "icml_2025",
    "neurips_2025": "neurips_2025",
    "iclr_2026": "iclr_2026",
    "aaai_2025": "aaai_2025",
    "acl_2025": "acl_2025",
    "nature_science": "nature",
    "ieee_transactions": "ieee",
}


def get_style_for_profile(profile_id: str) -> LaTeXStyle:
    """Get the LaTeX style for a profile ID.

    Falls back to 'default' if no specific style is registered.
    """
    # Direct match
    if profile_id in STYLE_REGISTRY:
        return STYLE_REGISTRY[profile_id]

    # Profile mapping
    style_key = PROFILE_STYLE_MAP.get(profile_id)
    if style_key and style_key in STYLE_REGISTRY:
        return STYLE_REGISTRY[style_key]

    # Fuzzy match
    profile_lower = profile_id.lower()
    for key, style in STYLE_REGISTRY.items():
        if key in profile_lower or profile_lower in key:
            return style

    return STYLE_REGISTRY["default"]


def list_available_styles() -> List[str]:
    """List all registered style names."""
    return list(STYLE_REGISTRY.keys())


def get_preamble(profile_id: str) -> str:
    """Generate LaTeX preamble for a profile."""
    style = get_style_for_profile(profile_id)

    if style.document_class != "article":
        doc_class = f"\\documentclass[{style.options}]{{{style.document_class}}}"
    elif style.options:
        doc_class = f"\\documentclass[{style.options}]{{article}}"
    else:
        doc_class = "\\documentclass{article}"

    lines = [
        doc_class,
        "",
        "% Packages",
        "\\usepackage[utf8]{inputenc}",
        "\\usepackage{amsmath,amssymb,amsthm}",
        "\\usepackage{graphicx}",
        "\\usepackage{hyperref}",
        "\\usepackage{natbib}",
        "\\usepackage{booktabs}",
        "\\usepackage{algorithm,algorithmic}",
    ]

    if style.sty_path:
        lines.append(f"\\usepackage{{{style.sty_file.replace('.sty', '')}}}")

    lines.extend([
        "",
        "% Theorem environments",
        "\\newtheorem{theorem}{Theorem}",
        "\\newtheorem{lemma}[theorem]{Lemma}",
        "\\newtheorem{definition}{Definition}",
        "",
    ])

    return "\n".join(lines)

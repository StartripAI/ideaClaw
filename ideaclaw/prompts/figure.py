"""Figure generation prompts — instructions for automated figure creation.

Covers:
  - Figure code generation (matplotlib/plotly)
  - Figure critique and refinement
  - Caption generation
  - Figure placement suggestions
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

__all__ = ["FIGURE_CODEGEN_SYSTEM", "FIGURE_CODEGEN_TEMPLATE", "FIGURE_TYPES", "FIGURE_CRITIQUE_SYSTEM", "FIGURE_CRITIQUE_TEMPLATE", "CAPTION_TEMPLATE", "FIGURE_PLACEMENT_TEMPLATE", "get_figure_codegen_prompt", "get_figure_critique_prompt", "get_caption_prompt"]


FIGURE_CODEGEN_SYSTEM = """\
You are an expert scientific figure designer. You generate Python code
(matplotlib or plotly) that produces publication-quality figures.

Design principles:
- Clean, minimal design — no chartjunk
- Colorblind-friendly palettes (use seaborn 'colorblind' or viridis)
- High DPI (300) for print quality
- Proper font sizes: title 14pt, axis labels 12pt, tick labels 10pt
- LaTeX-compatible fonts when possible (serif family)
- Consistent with top-tier venue submission guidelines
"""

FIGURE_CODEGEN_TEMPLATE = """\
Generate Python code to create a {figure_type} figure.

SPECIFICATION:
- Title: {title}
- Description: {description}
- Data: {data}
- Style: {style}
- Output format: {output_format}
- Dimensions: {width}×{height} inches

REQUIREMENTS:
1. Use matplotlib (always available). Optionally use seaborn for styling.
2. The code must be self-contained — include all imports.
3. Save to the path: "{output_path}"
4. Use plt.tight_layout() before saving.
5. Set DPI=300 for publication quality.
6. Add proper axis labels, legend (if >1 series), and title.
7. Use a professional color palette.
8. For bar charts: add value labels on top of bars.
9. For line charts: add markers at data points.
10. For heatmaps: use a perceptually uniform colormap (viridis/plasma).

Return ONLY the Python code, no explanations.
"""

FIGURE_TYPES = {
    "bar": "Vertical or horizontal bar chart for comparing categorical data",
    "line": "Line chart for showing trends over time or continuous variables",
    "scatter": "Scatter plot for showing relationships between two variables",
    "heatmap": "Heatmap for showing intensity across two categorical dimensions",
    "box": "Box plot for showing distributions across categories",
    "violin": "Violin plot for showing distribution shape across categories",
    "radar": "Radar/spider chart for comparing multiple dimensions",
    "histogram": "Histogram for showing frequency distributions",
    "pie": "Pie chart (use sparingly) for showing proportions",
    "area": "Stacked area chart for showing composition over time",
    "architecture": "Architecture diagram showing system components and data flow",
    "flowchart": "Flowchart showing process steps and decision points",
    "comparison_table": "Formatted comparison table as a figure",
}

FIGURE_CRITIQUE_SYSTEM = """\
You are a scientific figure critic. You evaluate figures for:
- Clarity: Can the reader understand the message instantly?
- Accuracy: Does the visualization faithfully represent the data?
- Aesthetics: Is it visually appealing and professional?
- Standards: Does it meet publication standards?

Be specific about what to fix — reference exact elements.
"""

FIGURE_CRITIQUE_TEMPLATE = """\
Critique this figure for a {venue} submission.

FIGURE DESCRIPTION:
{description}

FIGURE CODE:
```python
{code}
```

CURRENT ISSUES TO CHECK:
1. Font sizes appropriate for column/page width?
2. Color palette accessible (colorblind-friendly)?
3. Axis labels clear and complete (with units)?
4. Legend properly positioned and not overlapping data?
5. Statistical annotations present (error bars, significance)?
6. Consistent with journal style guidelines?
7. Caption-worthy — can you suggest a good caption?

Provide:
## Issues Found
(numbered list)

## Suggested Fixes
(for each issue, specific code changes)

## Suggested Caption
(2-3 sentence caption)

## Revised Code
```python
(complete fixed code)
```
"""

CAPTION_TEMPLATE = """\
Generate a figure caption for this {figure_type}.

TITLE: {title}
DESCRIPTION: {description}
KEY FINDINGS: {findings}

The caption should:
1. Start with a bold descriptive title
2. Describe what the figure shows (1-2 sentences)
3. Highlight the key takeaway (1 sentence)
4. Note any methodological details (sample size, error bars)
5. Be self-contained — understandable without reading the main text

Format: **[Title].** [Description]. [Key finding]. [Methods note].
"""

FIGURE_PLACEMENT_TEMPLATE = """\
Given this paper outline and list of figures, suggest optimal placement.

PAPER OUTLINE:
{outline}

FIGURES:
{figures}

For each figure, suggest:
1. Which section it belongs in
2. Where in the section (beginning, middle, end)
3. Whether it should be a full-width or column-width figure
4. The ideal \\label{{}} and \\ref{{}} text
"""


def get_figure_codegen_prompt(
    figure_type: str = "bar",
    title: str = "",
    description: str = "",
    data: str = "{}",
    style: str = "academic",
    output_path: str = "/tmp/figure.png",
    output_format: str = "png",
    width: float = 6.0,
    height: float = 4.0,
) -> dict:
    """Get a figure code generation prompt."""
    return {
        "system": FIGURE_CODEGEN_SYSTEM,
        "user": FIGURE_CODEGEN_TEMPLATE.format(
            figure_type=FIGURE_TYPES.get(figure_type, figure_type),
            title=title,
            description=description,
            data=data,
            style=style,
            output_path=output_path,
            output_format=output_format,
            width=width,
            height=height,
        ),
    }


def get_figure_critique_prompt(
    description: str, code: str, venue: str = "NeurIPS",
) -> dict:
    """Get a figure critique prompt."""
    return {
        "system": FIGURE_CRITIQUE_SYSTEM,
        "user": FIGURE_CRITIQUE_TEMPLATE.format(
            description=description, code=code, venue=venue,
        ),
    }


def get_caption_prompt(
    figure_type: str, title: str, description: str, findings: str = "",
) -> dict:
    """Get a caption generation prompt."""
    return {
        "system": "You write concise, informative scientific figure captions.",
        "user": CAPTION_TEMPLATE.format(
            figure_type=figure_type, title=title,
            description=description, findings=findings or "(not specified)",
        ),
    }

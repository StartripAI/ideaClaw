"""Figure Agent — automated figure generation with codegen→render→critique→refine loop.

Upgraded from export/figure_agent.py (198L) to a full-featured agent:
  - LLM-powered code generation (matplotlib/plotly)
  - Sandbox execution with error recovery
  - Multi-round critique and refinement
  - 13 figure types, 3 styles
  - PNG/SVG/PDF output

Usage:
    from ideaclaw.agents.figure_agent import FigureAgent, FigureSpec

logger = logging.getLogger(__name__)

__all__ = ['FigureSpec', 'FigureResult', 'FigureAgent']

    agent = FigureAgent(llm_callable=my_llm)
    spec = FigureSpec(figure_id="fig1", figure_type="bar", title="Results",
                      data={"labels": ["A","B"], "values": [0.8, 0.9]})
    result = agent.generate(spec, output_dir=Path("./figures"))
"""

from __future__ import annotations
import logging

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ideaclaw.prompts.figure import (
    get_figure_codegen_prompt,
    get_figure_critique_prompt,
    get_caption_prompt,
    FIGURE_TYPES,
)


@dataclass
class FigureSpec:
    """Specification for a figure to generate."""
    figure_id: str
    figure_type: str              # bar|line|scatter|heatmap|radar|...
    title: str
    data: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    style: str = "academic"       # academic|minimal|colorful
    width: float = 6.0
    height: float = 4.0
    output_format: str = "png"    # png|svg|pdf


@dataclass
class FigureResult:
    """Result from figure generation."""
    figure_id: str
    image_path: str = ""
    code: str = ""
    caption: str = ""
    critique: str = ""
    iterations: int = 0
    success: bool = False
    error: str = ""


class FigureAgent:
    """Automated figure generation agent with critique loop.

    Works in two modes:
    1. LLM mode: Uses an LLM callable to generate matplotlib/plotly code
    2. Heuristic mode: Uses built-in templates (no LLM needed)
    """

    MAX_CRITIQUE_ROUNDS = 3

    def __init__(
        self,
        llm_callable: Optional[Callable[[str], str]] = None,
        max_rounds: int = 3,
        timeout: int = 30,
    ):
        self.llm = llm_callable
        self.max_rounds = min(max_rounds, self.MAX_CRITIQUE_ROUNDS)
        self.timeout = timeout

    def generate(
        self,
        spec: FigureSpec,
        output_dir: Path = Path("/tmp/ideaclaw_figures"),
        critique: bool = True,
    ) -> FigureResult:
        """Generate a figure from specification.

        Pipeline:
        1. Generate code (LLM or template)
        2. Execute in sandbox
        3. If critique enabled: LLM critiques → refine → re-execute
        4. Generate caption

        Args:
            spec: FigureSpec with type, data, style, etc.
            output_dir: Where to save the output image.
            critique: Whether to run the critique→refine loop.

        Returns:
            FigureResult with image path, code, caption.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{spec.figure_id}.{spec.output_format}"

        # Step 1: Generate code
        if self.llm:
            code = self._llm_codegen(spec, str(output_path))
        else:
            code = self._template_codegen(spec, str(output_path))

        if not code:
            return FigureResult(figure_id=spec.figure_id, error="Code generation failed")

        # Step 2: Execute
        success, error = self._execute(code, output_path)
        iterations = 1

        # Step 3: Critique loop (if LLM available and enabled)
        if self.llm and critique:
            for round_i in range(self.max_rounds):
                if success and output_path.exists():
                    # Get critique
                    critique_text = self._critique(spec, code)
                    if not critique_text or "no issues" in critique_text.lower():
                        break
                    # Refine code
                    code = self._refine(code, critique_text, spec, str(output_path))
                    success, error = self._execute(code, output_path)
                    iterations += 1
                elif not success:
                    # Fix error
                    code = self._fix_error(code, error, spec, str(output_path))
                    success, error = self._execute(code, output_path)
                    iterations += 1

        # Step 4: Generate caption
        caption = ""
        if self.llm and success:
            caption = self._generate_caption(spec)

        return FigureResult(
            figure_id=spec.figure_id,
            image_path=str(output_path) if success else "",
            code=code,
            caption=caption,
            critique="" if not critique else "Critique loop completed",
            iterations=iterations,
            success=success,
            error=error if not success else "",
        )

    def generate_batch(
        self,
        specs: List[FigureSpec],
        output_dir: Path = Path("/tmp/ideaclaw_figures"),
    ) -> List[FigureResult]:
        """Generate multiple figures."""
        return [self.generate(spec, output_dir) for spec in specs]

    # ---- Internal ----

    def _llm_codegen(self, spec: FigureSpec, output_path: str) -> str:
        """Generate figure code using LLM."""
        prompt = get_figure_codegen_prompt(
            figure_type=spec.figure_type,
            title=spec.title,
            description=spec.description,
            data=json.dumps(spec.data, indent=2),
            style=spec.style,
            output_path=output_path,
            output_format=spec.output_format,
            width=spec.width,
            height=spec.height,
        )
        response = self.llm(f"{prompt['system']}\n\n{prompt['user']}")
        return self._extract_code(response)

    def _template_codegen(self, spec: FigureSpec, output_path: str) -> str:
        """Generate figure code from built-in templates (no LLM needed)."""
        data = spec.data
        templates = {
            "bar": self._template_bar,
            "line": self._template_line,
            "scatter": self._template_scatter,
            "heatmap": self._template_heatmap,
            "radar": self._template_radar,
            "histogram": self._template_histogram,
        }
        gen_fn = templates.get(spec.figure_type, self._template_bar)
        return gen_fn(spec, output_path)

    def _execute(self, code: str, output_path: Path) -> tuple:
        """Execute Python code in a subprocess sandbox."""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8",
            ) as f:
                f.write(code)
                f.flush()
                result = subprocess.run(
                    [sys.executable, f.name],
                    capture_output=True, text=True, timeout=self.timeout,
                )
            if result.returncode == 0 and output_path.exists():
                return True, ""
            return False, result.stderr or result.stdout or "Unknown error"
        except subprocess.TimeoutExpired:
            return False, f"Execution timed out ({self.timeout}s)"
        except Exception as e:
            return False, str(e)

    def _critique(self, spec: FigureSpec, code: str) -> str:
        """Get LLM critique of generated figure."""
        prompt = get_figure_critique_prompt(
            description=f"{spec.title}: {spec.description}",
            code=code,
        )
        return self.llm(f"{prompt['system']}\n\n{prompt['user']}")

    def _refine(self, code: str, critique: str, spec: FigureSpec, output_path: str) -> str:
        """Refine code based on critique."""
        prompt = (
            f"Revise this matplotlib code based on the critique.\n\n"
            f"ORIGINAL CODE:\n```python\n{code}\n```\n\n"
            f"CRITIQUE:\n{critique}\n\n"
            f"Output path must be: {output_path}\n\n"
            f"Return ONLY the revised Python code."
        )
        response = self.llm(prompt)
        return self._extract_code(response) or code

    def _fix_error(self, code: str, error: str, spec: FigureSpec, output_path: str) -> str:
        """Fix code based on execution error."""
        prompt = (
            f"Fix this Python code that produced an error.\n\n"
            f"CODE:\n```python\n{code}\n```\n\n"
            f"ERROR:\n{error}\n\n"
            f"Output path: {output_path}\n"
            f"Return ONLY the fixed Python code."
        )
        response = self.llm(prompt)
        return self._extract_code(response) or code

    def _generate_caption(self, spec: FigureSpec) -> str:
        """Generate figure caption using LLM."""
        prompt = get_caption_prompt(
            figure_type=spec.figure_type,
            title=spec.title,
            description=spec.description,
        )
        return self.llm(f"{prompt['system']}\n\n{prompt['user']}")

    @staticmethod
    def _extract_code(response: str) -> str:
        """Extract Python code from LLM response."""
        # Try fenced code block first
        m = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
        if m:
            return m.group(1).strip()
        # If response looks like code itself
        if "import " in response and "plt." in response:
            return response.strip()
        return ""

    # ---- Built-in Templates ----

    @staticmethod
    def _template_bar(spec: FigureSpec, output_path: str) -> str:
        labels = json.dumps(spec.data.get("labels", ["A", "B", "C"]))
        values = json.dumps(spec.data.get("values", [1, 2, 3]))
        return textwrap.dedent(f"""\
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')

        labels = {labels}
        values = {values}
        colors = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00']

        fig, ax = plt.subplots(figsize=({spec.width}, {spec.height}))
        bars = ax.bar(labels, values, color=colors[:len(labels)], edgecolor='white', linewidth=0.8)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
                    f'{{val:.2f}}', ha='center', va='bottom', fontsize=10)
        ax.set_title({json.dumps(spec.title)}, fontsize=14, fontweight='bold')
        ax.set_ylabel('Value')
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=0.3)
        fig.tight_layout()
        fig.savefig({json.dumps(output_path)}, dpi=300, bbox_inches='tight')
        plt.close()
        """)

    @staticmethod
    def _template_line(spec: FigureSpec, output_path: str) -> str:
        x = json.dumps(spec.data.get("x", list(range(1, 11))))
        y = json.dumps(spec.data.get("y", [0.1, 0.3, 0.5, 0.6, 0.65, 0.7, 0.75, 0.78, 0.8, 0.82]))
        return textwrap.dedent(f"""\
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')

        x = {x}
        y = {y}
        fig, ax = plt.subplots(figsize=({spec.width}, {spec.height}))
        ax.plot(x, y, '-o', color='#0072B2', linewidth=2, markersize=6)
        ax.set_title({json.dumps(spec.title)}, fontsize=14, fontweight='bold')
        ax.set_xlabel('X'); ax.set_ylabel('Y')
        ax.spines[['top','right']].set_visible(False)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig({json.dumps(output_path)}, dpi=300)
        plt.close()
        """)

    @staticmethod
    def _template_scatter(spec: FigureSpec, output_path: str) -> str:
        x = json.dumps(spec.data.get("x", [1, 2, 3, 4, 5]))
        y = json.dumps(spec.data.get("y", [2, 3, 5, 4, 6]))
        return textwrap.dedent(f"""\
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')

        fig, ax = plt.subplots(figsize=({spec.width}, {spec.height}))
        ax.scatter({x}, {y}, s=80, c='#0072B2', alpha=0.7, edgecolors='white')
        ax.set_title({json.dumps(spec.title)}, fontsize=14, fontweight='bold')
        ax.spines[['top','right']].set_visible(False)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig({json.dumps(output_path)}, dpi=300)
        plt.close()
        """)

    @staticmethod
    def _template_heatmap(spec: FigureSpec, output_path: str) -> str:
        data = json.dumps(spec.data.get("matrix", [[0.8, 0.6], [0.4, 0.9]]))
        xlabels = json.dumps(spec.data.get("xlabels", ["A", "B"]))
        ylabels = json.dumps(spec.data.get("ylabels", ["X", "Y"]))
        return textwrap.dedent(f"""\
        import matplotlib.pyplot as plt
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')

        data = np.array({data})
        fig, ax = plt.subplots(figsize=({spec.width}, {spec.height}))
        im = ax.imshow(data, cmap='viridis', vmin=0, vmax=1)
        ax.set_xticks(range(data.shape[1]))
        ax.set_xticklabels({xlabels})
        ax.set_yticks(range(data.shape[0]))
        ax.set_yticklabels({ylabels})
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                ax.text(j, i, f'{{data[i,j]:.2f}}', ha='center', va='center', color='white' if data[i,j]>0.5 else 'black')
        fig.colorbar(im, ax=ax)
        ax.set_title({json.dumps(spec.title)}, fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig({json.dumps(output_path)}, dpi=300)
        plt.close()
        """)

    @staticmethod
    def _template_radar(spec: FigureSpec, output_path: str) -> str:
        labels = json.dumps(spec.data.get("labels", ["A", "B", "C", "D"]))
        values = json.dumps(spec.data.get("values", [0.8, 0.6, 0.9, 0.7]))
        return textwrap.dedent(f"""\
        import matplotlib.pyplot as plt
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')

        labels = {labels}
        values = {values}
        N = len(labels)
        angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
        values_c = values + [values[0]]
        angles_c = angles + [angles[0]]
        fig, ax = plt.subplots(figsize=({spec.width}, {spec.height}), subplot_kw=dict(polar=True))
        ax.fill(angles_c, values_c, alpha=0.25, color='#0072B2')
        ax.plot(angles_c, values_c, 'o-', color='#0072B2', linewidth=2)
        ax.set_xticks(angles)
        ax.set_xticklabels(labels)
        ax.set_ylim(0, 1)
        ax.set_title({json.dumps(spec.title)}, fontsize=14, fontweight='bold', pad=20)
        fig.tight_layout()
        fig.savefig({json.dumps(output_path)}, dpi=300)
        plt.close()
        """)

    @staticmethod
    def _template_histogram(spec: FigureSpec, output_path: str) -> str:
        data = json.dumps(spec.data.get("values", [1, 2, 2, 3, 3, 3, 4, 4, 5]))
        return textwrap.dedent(f"""\
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')

        data = {data}
        fig, ax = plt.subplots(figsize=({spec.width}, {spec.height}))
        ax.hist(data, bins='auto', color='#0072B2', edgecolor='white', alpha=0.8)
        ax.set_title({json.dumps(spec.title)}, fontsize=14, fontweight='bold')
        ax.set_xlabel('Value'); ax.set_ylabel('Frequency')
        ax.spines[['top','right']].set_visible(False)
        fig.tight_layout()
        fig.savefig({json.dumps(output_path)}, dpi=300)
        plt.close()
        """)

"""Figure Agent — automated figure generation for papers.

Surpasses ARC's 8-file figure_agent by consolidating into a single
orchestrator with codegen→render→critique→refine loop.
Works with LLM (real code generation) and heuristic (matplotlib templates).
"""
from __future__ import annotations
import logging
import json, textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from ideaclaw.sandbox.executor import SandboxExecutor, SandboxConfig, ExecResult

logger = logging.getLogger(__name__)

__all__ = ['FigureSpec', 'FigureResult', 'TEMPLATES', 'FigureAgent']


@dataclass
class FigureSpec:
    """Specification for a figure to generate."""
    figure_id: str
    figure_type: str  # bar|line|heatmap|scatter|diagram|table|architecture
    title: str
    data: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    style: str = "academic"  # academic|minimal|colorful


@dataclass
class FigureResult:
    """Result from figure generation."""
    figure_id: str
    image_path: str = ""
    code: str = ""
    success: bool = False
    critique: str = ""
    iterations: int = 0
    error: str = ""


# Pre-built matplotlib templates for common figure types
TEMPLATES = {
    "bar": textwrap.dedent("""
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt, json, sys
        data = json.loads(sys.argv[1])
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(data['labels'], data['values'], color='#4285F4', edgecolor='white')
        ax.set_ylabel(data.get('ylabel', 'Value'), fontsize=12)
        ax.set_title(data.get('title', 'Figure'), fontsize=14, fontweight='bold')
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y', alpha=0.3)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig('figure.png', dpi=200, bbox_inches='tight')
        print(json.dumps({"status":"ok","path":"figure.png"}))
    """).strip(),
    "line": textwrap.dedent("""
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt, json, sys
        data = json.loads(sys.argv[1])
        fig, ax = plt.subplots(figsize=(8, 5))
        for series in data.get('series', [{'values': data.get('values',[])}]):
            label = series.get('label', '')
            ax.plot(series['values'], '-o', label=label, linewidth=2, markersize=5)
        ax.set_xlabel(data.get('xlabel', 'Step'), fontsize=12)
        ax.set_ylabel(data.get('ylabel', 'Value'), fontsize=12)
        ax.set_title(data.get('title', 'Figure'), fontsize=14, fontweight='bold')
        if len(data.get('series', [])) > 1: ax.legend(frameon=False)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig('figure.png', dpi=200, bbox_inches='tight')
        print(json.dumps({"status":"ok","path":"figure.png"}))
    """).strip(),
    "heatmap": textwrap.dedent("""
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt, numpy as np, json, sys
        data = json.loads(sys.argv[1])
        matrix = np.array(data['matrix'])
        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
        plt.colorbar(im)
        if 'xlabels' in data: ax.set_xticks(range(len(data['xlabels']))); ax.set_xticklabels(data['xlabels'], rotation=45, ha='right')
        if 'ylabels' in data: ax.set_yticks(range(len(data['ylabels']))); ax.set_yticklabels(data['ylabels'])
        ax.set_title(data.get('title', 'Heatmap'), fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig('figure.png', dpi=200, bbox_inches='tight')
        print(json.dumps({"status":"ok","path":"figure.png"}))
    """).strip(),
}


class FigureAgent:
    """Generate publication-quality figures with codegen→render→critique loop.

    Usage:
        agent = FigureAgent()
        spec = FigureSpec("fig1", "bar", "Model Comparison",
                          data={"labels": ["A","B","C"], "values": [0.9, 0.85, 0.7]})
        result = agent.generate(spec)
    """

    def __init__(self, llm_call: Optional[Callable] = None, max_iterations: int = 3):
        self.llm_call = llm_call
        self.max_iterations = max_iterations
        self.executor = SandboxExecutor(SandboxConfig(timeout_seconds=30))

    def generate(self, spec: FigureSpec) -> FigureResult:
        """Generate a figure from specification."""
        result = FigureResult(figure_id=spec.figure_id)

        for iteration in range(1, self.max_iterations + 1):
            result.iterations = iteration

            # Step 1: Generate code
            if self.llm_call and iteration > 1:
                code = self._codegen_llm(spec, result.critique)
            else:
                code = self._codegen_template(spec)
            result.code = code

            # Step 2: Render (execute in sandbox)
            data_json = json.dumps(spec.data)
            exec_result = self.executor.run_script(
                f"gen_{spec.figure_id}.py", code, args=[data_json]
            )

            if exec_result.success:
                # Find generated image
                images = [a for a in exec_result.artifacts if a.endswith(('.png', '.pdf', '.svg'))]
                if images:
                    result.image_path = images[0]
                    result.success = True
                    # Step 3: Critique (only if LLM available and not last iteration)
                    if self.llm_call and iteration < self.max_iterations:
                        critique = self._critique(spec, code)
                        if "PASS" in critique.upper():
                            break
                        result.critique = critique
                    else:
                        break
                else:
                    result.error = "No image file generated"
                    result.critique = f"Code ran but no image produced. stdout: {exec_result.stdout[:200]}"
            else:
                result.error = exec_result.stderr[:500]
                result.critique = f"Execution failed: {exec_result.stderr[:300]}"
                if not self.llm_call:
                    break  # Can't fix without LLM

        return result

    def generate_batch(self, specs: List[FigureSpec]) -> List[FigureResult]:
        """Generate multiple figures."""
        return [self.generate(spec) for spec in specs]

    def _codegen_template(self, spec: FigureSpec) -> str:
        """Generate code from built-in templates."""
        template = TEMPLATES.get(spec.figure_type, TEMPLATES["bar"])
        return template

    def _codegen_llm(self, spec: FigureSpec, critique: str = "") -> str:
        prompt = (
            f"Generate matplotlib Python code for a {spec.figure_type} figure.\n"
            f"Title: {spec.title}\nDescription: {spec.description}\n"
            f"Data format: JSON passed as sys.argv[1]\n"
            f"Data example: {json.dumps(spec.data)[:300]}\n"
            f"Style: {spec.style}, publication-quality, 200 DPI\n"
            f"Save to 'figure.png'. Print JSON {{\"status\":\"ok\"}} when done.\n"
        )
        if critique:
            prompt += f"\nPrevious critique to address:\n{critique}\n"
        response = self.llm_call(
            system_prompt="Expert matplotlib code generator. Output ONLY Python code.",
            user_prompt=prompt,
        )
        # Extract code from response
        if "```python" in response:
            code = response.split("```python")[1].split("```")[0]
        elif "```" in response:
            code = response.split("```")[1].split("```")[0]
        else:
            code = response
        return code.strip()

    def _critique(self, spec: FigureSpec, code: str) -> str:
        if not self.llm_call:
            return "PASS"
        prompt = (
            f"Critique this matplotlib code for a {spec.figure_type} figure titled '{spec.title}'.\n"
            f"Check: 1) Academic quality 2) Readable labels 3) Color accessibility 4) Legend clarity\n"
            f"Code:\n{code[:1000]}\n\nReply PASS if good, or describe specific issues."
        )
        return self.llm_call(
            system_prompt="Academic figure quality critic.",
            user_prompt=prompt,
        )

    def cleanup(self):
        self.executor.cleanup()

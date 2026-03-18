"""Pack builder — assembles final pack content from pipeline outputs.

Uses Jinja2 templates + quality profile to produce the final pack.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ideaclaw.pack.schema import PackType

TEMPLATES_DIR = Path(__file__).parent / "templates"


class PackBuilder:
    """Assembles pack content from pipeline stage outputs."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(disabled_extensions=("md.j2",)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def build(self, pipeline_context: Dict[str, Any]) -> Dict[str, Any]:
        """Build the final pack from accumulated pipeline context.

        Args:
            pipeline_context: Dict with keys from each pipeline stage:
                - idea: original idea text
                - pack_type: PackType or string
                - decomposition: MECE decomposition result
                - sources: list of sources found
                - evidence: extracted evidence
                - synthesis: evidence synthesis
                - decision_tree: reasoning tree
                - counterarguments: list of counterarguments
                - draft: raw draft from LLM
                - trust_review: TrustReviewResult

        Returns:
            Dict with 'markdown', 'json', and 'metadata' keys.
        """
        # Resolve pack type
        pack_type = pipeline_context.get("pack_type", "decision")
        if isinstance(pack_type, str):
            try:
                pt = PackType.from_string(pack_type)
            except ValueError:
                pt = PackType.DECISION
        else:
            pt = pack_type

        # Build template context
        ctx = self._build_context(pipeline_context, pt)

        # Render markdown
        template_name = pt.info.template
        try:
            template = self.env.get_template(template_name)
        except Exception:
            # Fallback to generic template
            template = self.env.get_template("generic.md.j2")

        markdown = template.render(**ctx)

        # Build JSON structure
        pack_json = self._build_json(pipeline_context, pt, ctx)

        return {
            "markdown": markdown,
            "json": pack_json,
            "metadata": {
                "pack_type": pt.info.name,
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "profile_id": self.config.get("quality", {}).get("profile_id", ""),
                "idea": pipeline_context.get("idea", ""),
            },
        }

    def _build_context(self, ctx: Dict, pt: PackType) -> Dict[str, Any]:
        """Build Jinja2 template context from pipeline outputs."""
        idea = ctx.get("idea", "")
        profile_id = self.config.get("quality", {}).get("profile_id", "general.decision")
        run_id = ctx.get("run_id", "")
        version = "0.1.0"

        # Trust review data
        trust = ctx.get("trust_review")
        trust_data = {
            "pqs": getattr(trust, "overall_score", 0) if trust else 0,
            "verdict": getattr(trust, "verdict", "N/A") if trust else "N/A",
            "evidence_coverage": ctx.get("evidence_coverage", 0),
        }

        # Sources
        sources = ctx.get("sources", [])
        if isinstance(sources, str):
            sources = [{"title": s.strip(), "url": ""} for s in sources.split("\n") if s.strip()]

        # Claims
        claims = ctx.get("claims", [])
        if not claims and ctx.get("synthesis"):
            claims = self._extract_claims(ctx["synthesis"])

        return {
            "idea": idea,
            "pack_type": pt.info.name,
            "profile_id": profile_id,
            "run_id": run_id,
            "version": version,
            "date": dt.date.today().isoformat(),
            "trust": trust_data,
            "conclusion": ctx.get("conclusion", ctx.get("draft", "")),
            "reasoning": ctx.get("reasoning", ctx.get("synthesis", "")),
            "counterarguments": ctx.get("counterarguments", []),
            "uncertainties": ctx.get("uncertainties", []),
            "action_items": ctx.get("action_items", []),
            "sources": sources,
            "claims": claims,
            "decomposition": ctx.get("decomposition", {}),
            "decision_tree": ctx.get("decision_tree", {}),
            "draft": ctx.get("draft", ""),
            # Proposal-specific
            "executive_summary": ctx.get("executive_summary", ""),
            "background": ctx.get("background", ""),
            "proposal": ctx.get("proposal", ""),
            "risks": ctx.get("risks", []),
            "timeline": ctx.get("timeline", ""),
            # Comparison-specific
            "options": ctx.get("options", []),
            "comparison_matrix": ctx.get("comparison_matrix", ""),
            "recommendation": ctx.get("recommendation", ""),
            # Study-specific
            "methodology": ctx.get("methodology", ""),
            "findings": ctx.get("findings", ""),
            "limitations": ctx.get("limitations", []),
        }

    def _build_json(self, ctx: Dict, pt: PackType, template_ctx: Dict) -> Dict:
        """Build machine-readable JSON pack structure."""
        return {
            "schema_version": "1.0",
            "pack_type": pt.info.name,
            "idea": ctx.get("idea", ""),
            "profile_id": template_ctx.get("profile_id", ""),
            "generated_at": template_ctx["date"],
            "trust": template_ctx["trust"],
            "sections": {s: template_ctx.get(s, "") for s in pt.info.sections},
            "sources": template_ctx["sources"],
            "claims": template_ctx["claims"],
        }

    def _extract_claims(self, synthesis: str) -> List[Dict]:
        """Extract claims from synthesis text (heuristic)."""
        import re
        claims = []
        for line in synthesis.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Look for evidence-marked claims
            status = "inferred"
            if "✅" in line:
                status = "evidenced"
            elif "⚠️" in line:
                status = "inferred"
            elif "🚫" in line:
                status = "unsupported"
            if len(line) > 20:
                claims.append({"text": line[:200], "status": status})
        return claims[:20]  # Cap at 20 claims

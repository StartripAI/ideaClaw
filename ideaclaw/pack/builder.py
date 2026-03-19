"""Pack builder — assembles final pack content from pipeline outputs.

Uses Jinja2 templates + quality profile to produce the final pack.
"""

from __future__ import annotations
import logging

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ideaclaw.pack.schema import PackType

logger = logging.getLogger(__name__)

__all__ = ['TEMPLATES_DIR', 'PackBuilder']

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
                - deliverable_template: (optional) template content from TemplateLoader
                - deliverable_sections: (optional) section names from template
                - deliverable_format: (optional) 'latex', 'markdown', or 'fountain'
                - review_form: (optional) review criteria from TemplateLoader
                - template_tier: (optional) tier identifier

        Returns:
            Dict with 'markdown', 'json', and 'metadata' keys.
        """
        # If deliverable template is available, use template-driven build
        if pipeline_context.get("deliverable_template"):
            return self._build_from_deliverable_template(pipeline_context)

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
        except Exception:  # noqa: BLE001
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

    def _build_from_deliverable_template(
        self, pipeline_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build output using a deliverable template from TemplateLoader.

        Uses the template skeleton to produce a structured, professional
        deliverable where each section is filled from the pipeline draft.
        """
        template_content = pipeline_context["deliverable_template"]
        sections = pipeline_context.get("deliverable_sections", [])
        fmt = pipeline_context.get("deliverable_format", "markdown")
        tier = pipeline_context.get("template_tier", "unknown")
        draft = pipeline_context.get("draft", "")
        idea = pipeline_context.get("idea", "")
        review_form = pipeline_context.get("review_form", {})

        # Parse draft into section content blocks
        section_content = self._split_draft_into_sections(draft, sections)

        # Fill template with section content
        if fmt == "latex":
            filled = self._fill_latex_template(template_content, section_content)
        else:
            filled = self._fill_markdown_template(template_content, section_content)

        # Build metadata
        metadata = {
            "pack_type": f"deliverable_{tier}",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "profile_id": self.config.get("scenario_id", self.config.get("quality", {}).get("profile_id", "")),
            "idea": idea,
            "deliverable_format": fmt,
            "template_tier": tier,
            "sections": sections,
            "review_form": review_form,
        }

        # Build JSON structure
        pack_json = {
            "schema_version": "2.0",
            "deliverable_type": tier,
            "format": fmt,
            "idea": idea,
            "profile_id": metadata["profile_id"],
            "generated_at": metadata["generated_at"],
            "sections": {s: section_content.get(s, "") for s in sections},
            "review_criteria": review_form.get("criteria", []) if review_form else [],
            "sources": pipeline_context.get("sources", []),
        }

        return {
            "markdown": filled if fmt != "latex" else draft,
            "latex": filled if fmt == "latex" else None,
            "json": pack_json,
            "metadata": metadata,
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

    # ------------------------------------------------------------------
    # Deliverable template helpers
    # ------------------------------------------------------------------

    def _split_draft_into_sections(
        self, draft: str, section_names: List[str]
    ) -> Dict[str, str]:
        """Split a draft into named sections by detecting headers.

        Handles both Markdown (## Section) and LaTeX (\\section{Section}) headers.
        """
        import re
        sections: Dict[str, str] = {}
        current_section = "_preamble"
        current_lines: List[str] = []

        for line in draft.split("\n"):
            # Detect markdown header
            md_match = re.match(r'^#{1,3}\s+(.+)', line)
            # Detect LaTeX section
            tex_match = re.match(r'\\(?:sub)?section\{(.+?)\}', line)

            header_name = None
            if md_match:
                header_name = md_match.group(1).strip()
            elif tex_match:
                header_name = tex_match.group(1).strip()

            if header_name:
                # Save previous section
                if current_lines:
                    sections[current_section] = "\n".join(current_lines).strip()
                # Match to known section name (fuzzy)
                matched = self._fuzzy_match_section(header_name, section_names)
                current_section = matched or header_name.lower().replace(" ", "_")
                current_lines = []
            else:
                current_lines.append(line)

        # Save last section
        if current_lines:
            sections[current_section] = "\n".join(current_lines).strip()

        return sections

    def _fuzzy_match_section(self, header: str, candidates: List[str]) -> Optional[str]:
        """Fuzzy-match a header to a section name."""
        header_lower = header.lower().replace(" ", "_").replace("-", "_")
        for c in candidates:
            c_lower = c.lower().replace(" ", "_").replace("-", "_")
            if c_lower == header_lower or c_lower in header_lower or header_lower in c_lower:
                return c
        return None

    def _fill_latex_template(
        self, template: str, sections: Dict[str, str]
    ) -> str:
        """Fill a LaTeX template by replacing section comment placeholders.

        Template format:
            \\section{Introduction}
            % CONSORT Item 2a: Scientific background...

        Replacement fills content after the section header.
        """
        import re
        lines = template.split("\n")
        output: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            output.append(line)

            # Check if this is a section header
            sec_match = re.match(r'\\(?:sub)?section\{(.+?)\}', line)
            if sec_match:
                sec_name = sec_match.group(1).strip()
                matched_key = self._fuzzy_match_section(sec_name, list(sections.keys()))
                if matched_key and sections.get(matched_key):
                    # Skip template comment lines (lines starting with %)
                    while i + 1 < len(lines) and lines[i + 1].strip().startswith("%"):
                        i += 1
                    # Insert generated content
                    output.append(sections[matched_key])
                    output.append("")  # blank line
            i += 1

        return "\n".join(output)

    def _fill_markdown_template(
        self, template: str, sections: Dict[str, str]
    ) -> str:
        """Fill a Markdown template by replacing placeholder sections.

        Template format:
            ## Section Name
            [Content]

        Replacement fills content after the section header.
        """
        import re
        lines = template.split("\n")
        output: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            header_match = re.match(r'^(#{1,3})\s+(.+)', line)

            if header_match:
                sec_name = header_match.group(2).strip()
                matched_key = self._fuzzy_match_section(sec_name, list(sections.keys()))
                output.append(line)
                if matched_key and sections.get(matched_key):
                    # Skip placeholder lines (lines with [Content] or [xxx])
                    while i + 1 < len(lines) and re.match(r'^\s*\[.+\]\s*$', lines[i + 1]):
                        i += 1
                    output.append("")  # blank line
                    output.append(sections[matched_key])
                    output.append("")  # blank line
            else:
                output.append(line)
            i += 1

        return "\n".join(output)

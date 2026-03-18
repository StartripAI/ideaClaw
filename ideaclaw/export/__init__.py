"""Export — Markdown, DOCX, PDF, JSON output formats.

Usage:
    from ideaclaw.export import Exporter
    exporter = Exporter(config)
    paths = exporter.export_all(pack_data, output_dir)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ideaclaw.export.markdown import MarkdownExporter
from ideaclaw.export.docx import DocxExporter


class Exporter:
    """Unified export manager."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.formats = config.get("export", {}).get("formats", ["markdown"])
        self.include_audit = config.get("export", {}).get("include_audit", True)
        self.include_sources = config.get("export", {}).get("include_sources", True)

    def export_all(
        self,
        pack_data: Dict[str, Any],
        output_dir: Path,
    ) -> List[Path]:
        """Export pack in all configured formats.

        Args:
            pack_data: Dict with 'markdown', 'json', 'metadata' from PackBuilder.
            output_dir: Directory to write outputs.

        Returns:
            List of paths to exported files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        exported = []

        markdown_content = pack_data.get("markdown", "")
        json_data = pack_data.get("json", {})
        metadata = pack_data.get("metadata", {})

        # Always export markdown (primary format)
        if "markdown" in self.formats:
            md_path = output_dir / "pack.md"
            MarkdownExporter().export(markdown_content, md_path)
            exported.append(md_path)

        # JSON manifest
        manifest_path = output_dir / "manifest.json"
        manifest = {
            **metadata,
            "quality": self.config.get("quality", {}),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        exported.append(manifest_path)

        # JSON pack data
        pack_json_path = output_dir / "pack.json"
        pack_json_path.write_text(
            json.dumps(json_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        exported.append(pack_json_path)

        # DOCX
        if "docx" in self.formats:
            docx_path = output_dir / "pack.docx"
            try:
                DocxExporter().export(markdown_content, docx_path)
                exported.append(docx_path)
            except ImportError:
                pass  # python-docx not installed

        # LaTeX (NeurIPS/ICML/ICLR/generic)
        if "latex" in self.formats:
            from ideaclaw.export.latex import LaTeXExporter
            template = self.config.get("export", {}).get("latex_template", "generic")
            latex_path = output_dir / "pack.tex"
            tex_meta = {
                "title": metadata.get("idea", "IdeaClaw Pack"),
                "authors": metadata.get("authors", ["IdeaClaw"]),
                "abstract": metadata.get("abstract", ""),
            }
            sources = json_data.get("sources", [])
            LaTeXExporter(template=template).export(
                markdown_content, latex_path,
                metadata=tex_meta, sources=sources,
            )
            exported.append(latex_path)
            bib_path = latex_path.with_suffix(".bib")
            if bib_path.exists():
                exported.append(bib_path)

        # Citation verification
        if self.config.get("export", {}).get("verify_citations", True):
            from ideaclaw.evidence.citation_verify import verify_citations, citation_summary
            cites = verify_citations(markdown_content)
            if cites:
                summary = citation_summary(cites)
                cite_path = output_dir / "citation_report.json"
                cite_path.write_text(
                    json.dumps(summary, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                exported.append(cite_path)

        # Trust review report (audit trail)
        if self.include_audit and "trust_review" in pack_data:
            audit_path = output_dir / "trust_review.json"
            audit_path.write_text(
                json.dumps(pack_data["trust_review"], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            exported.append(audit_path)

        return exported

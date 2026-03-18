"""PDF export — future implementation."""

from __future__ import annotations

from pathlib import Path


class PdfExporter:
    """Exports pack content as PDF. Future implementation."""

    def export(self, pack_content: str, output_path: Path) -> Path:
        """Write pack content to a PDF file.

        TODO: Implement with weasyprint.
        """
        raise NotImplementedError("PDF export not yet implemented. Install ideaclaw[pdf] when available.")

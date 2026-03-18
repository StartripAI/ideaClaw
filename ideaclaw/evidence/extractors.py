"""Multi-format evidence extractors.

TODO: Port from OpenRevise scripts/evidence_extractors.py
Supports: PDF, DOCX, PPTX, images (OCR), web pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvidenceCard:
    """A single piece of extracted evidence."""
    card_id: str
    claim: str
    quote: str
    source_id: str
    source_url: str = ""
    location: str = ""  # page number, slide number, URL fragment
    confidence: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    relevance_to: str = ""  # Which sub-question this answers
    verified: bool = False
    verification_note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvidenceExtractor:
    """Extracts structured evidence from multiple source formats.

    TODO: Port extraction logic from OpenRevise evidence_extractors.py:
    - PDF extraction (with GROBID fallback)
    - DOCX extraction
    - PPTX extraction
    - Image OCR (PaddleOCR + EasyOCR dual mode)
    - Web page extraction (new)
    """

    def __init__(self, config: Dict[str, Any]):
        self.ocr_mode = config.get("ocr_mode", "auto")

    def extract(self, source_path: str, source_type: str) -> List[EvidenceCard]:
        """Extract evidence cards from a source.

        TODO: Implement per-format extraction.
        """
        return []

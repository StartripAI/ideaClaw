"""T3: Evidence extraction tests (5 tests).

Tests PDF, DOCX, PPTX extraction, error handling, and local source dispatch.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from ideaclaw.evidence.extractors import (
    extract_pdf_text,
    extract_docx_text,
    extract_pptx_text_native,
    extract_local_source_text,
    ExtractResult,
)


def _make_minimal_docx(path: Path, text: str = "Hello DOCX World") -> None:
    """Create a minimal valid DOCX file."""
    doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", doc_xml)


def _make_minimal_pptx(path: Path, text: str = "Hello PPTX Slide") -> None:
    """Create a minimal valid PPTX file."""
    slide_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:sp><p:txBody>
    <a:p><a:r><a:t>{text}</a:t></a:r></a:p>
  </p:txBody></p:sp></p:spTree></p:cSld>
</p:sld>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("ppt/slides/slide1.xml", slide_xml)


# ---- T3.1: PDF extraction ----
def test_t3_1_pdf_extraction(tmp_dir):
    """T3.1: PDF extraction returns ExtractResult (text + detail)."""
    # Create a simple valid PDF
    pdf_path = tmp_dir / "test.pdf"
    pdf_content = b"""%PDF-1.0
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 100 700 Td (Hello PDF) Tj ET
endstream endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000360 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
431
%%EOF"""
    pdf_path.write_bytes(pdf_content)
    result = extract_pdf_text(str(pdf_path))
    assert isinstance(result, ExtractResult)
    # ExtractResult has text + detail fields
    assert hasattr(result, "text")
    assert hasattr(result, "detail")


# ---- T3.2: DOCX extraction ----
def test_t3_2_docx_extraction(tmp_dir):
    """T3.2: DOCX extraction returns expected text."""
    docx_path = tmp_dir / "test.docx"
    _make_minimal_docx(docx_path, "This is a test document with important evidence")
    result = extract_docx_text(str(docx_path))
    assert isinstance(result, ExtractResult)
    assert "test document" in result.text.lower(), f"Expected text not found: {result.text}"


# ---- T3.3: PPTX extraction ----
def test_t3_3_pptx_extraction(tmp_dir):
    """T3.3: PPTX extraction returns slide content."""
    pptx_path = tmp_dir / "test.pptx"
    _make_minimal_pptx(pptx_path, "Key findings from clinical trial")
    result = extract_pptx_text_native(str(pptx_path))
    assert isinstance(result, ExtractResult)
    assert "key findings" in result.text.lower() or "clinical" in result.text.lower()


# ---- T3.4: Corrupt file handling ----
def test_t3_4_corrupt_file_handling(tmp_dir):
    """T3.4: Corrupt file should not crash — returns result or raises handled exception."""
    bad_path = tmp_dir / "corrupt.pdf"
    bad_path.write_bytes(b"this is not a valid PDF file at all")
    try:
        result = extract_pdf_text(str(bad_path))
        # If it returns, text should be empty or detail should explain the error
        assert isinstance(result, ExtractResult)
    except Exception as exc:
        # If it raises, that's also acceptable — just shouldn't be an unhandled crash
        assert "pdf" in str(exc).lower() or "stream" in str(exc).lower() or "eof" in str(exc).lower()


# ---- T3.5: extract_local_source_text dispatcher ----
def test_t3_5_local_source_dispatch(tmp_dir):
    """T3.5: extract_local_source_text dispatches by source_type."""
    docx_path = tmp_dir / "evidence.docx"
    _make_minimal_docx(docx_path, "Evidence from local source document")
    result = extract_local_source_text(
        source_type="local_docx",
        path=docx_path,
        extract_mode="auto",
    )
    assert isinstance(result, ExtractResult)
    assert "evidence" in result.text.lower()

"""Evidence gate — verifies source reachability and evidence sufficiency.

Ported from OpenRevise scripts/check_revise_sources.py.
Supports: URL text, remote PDF, local PDF/DOCX/PPTX/image sources.
"""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ideaclaw.evidence.extractors import extract_local_source_text, ExtractResult


@dataclass
class GateCheckResult:
    """Result of checking a single source."""
    source_id: str
    tier: str  # "required" | "optional"
    ok: bool
    reachable: bool
    matched_tokens: int
    total_tokens: int
    detail: str
    evidence_excerpt: str = ""
    extraction_detail: str = ""


def fetch_url_text(
    url: str,
    timeout: int = 25,
    ca_bundle: Optional[str] = None,
    allow_insecure_tls: bool = False,
) -> str:
    """Fetch text content from a URL with curl fallback."""
    return fetch_url_bytes(
        url,
        timeout=timeout,
        ca_bundle=ca_bundle,
        allow_insecure_tls=allow_insecure_tls,
    ).decode("utf-8", errors="ignore")


def fetch_url_bytes(
    url: str,
    timeout: int = 25,
    ca_bundle: Optional[str] = None,
    allow_insecure_tls: bool = False,
) -> bytes:
    """Fetch raw bytes from a URL with curl fallback for TLS issues."""
    req = urllib.request.Request(url, headers={"User-Agent": "ideaclaw-source-check/1.0"})
    if allow_insecure_tls:
        context = ssl._create_unverified_context()
    elif ca_bundle:
        context = ssl.create_default_context(cafile=ca_bundle)
    else:
        context = None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Fallback to curl for environments with TLS trust store issues
        curl_cmd = ["curl", "-fsSL", "--max-time", str(timeout), "--retry", "1"]
        if ca_bundle:
            curl_cmd.extend(["--cacert", ca_bundle])
        if allow_insecure_tls:
            curl_cmd.append("-k")
        curl_cmd.append(url)
        proc = subprocess.run(curl_cmd, check=False, capture_output=True)
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore").strip()
            raise urllib.error.URLError(stderr or f"curl failed with exit code {proc.returncode}")
        return proc.stdout


def fetch_remote_pdf_text(
    url: str,
    timeout: int = 30,
    ca_bundle: Optional[str] = None,
    allow_insecure_tls: bool = False,
) -> str:
    """Download and extract text from a remote PDF."""
    from pypdf import PdfReader

    payload = fetch_url_bytes(
        url,
        timeout=timeout,
        ca_bundle=ca_bundle,
        allow_insecure_tls=allow_insecure_tls,
    )

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(payload)
        tmp.flush()
        reader = PdfReader(tmp.name)
        return "\n".join((page.extract_text() or "") for page in reader.pages)


def _normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy matching: join hyphenated words, collapse whitespace."""
    merged = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
    return re.sub(r"\s+", " ", merged).strip().lower()


def _make_excerpt(text: str, limit: int = 320) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3].rstrip() + "..."


def check_one_source(
    source_id: str,
    spec: Dict[str, Any],
    tier: str = "required",
    ca_bundle: Optional[str] = None,
    allow_insecure_tls: bool = False,
) -> GateCheckResult:
    """Check a single source for reachability and evidence token matching.

    Args:
        source_id: Identifier for this source.
        spec: Source specification dict with keys:
            - type: 'url_text' | 'remote_pdf' | 'local_pdf' | 'local_docx' | 'local_pptx' | 'local_image'
            - url or path: Location of the source
            - must_include: list of tokens that must be found
            - must_include_any: list where at least one must be found
            - extract_mode: 'auto' | 'native' | 'markitdown' | 'docling'
            - ocr_mode: 'dual' | 'paddle' | 'easy'
            - location_hints: e.g. ['page:1-3', 'slide:5']
        tier: 'required' or 'optional'

    Returns:
        GateCheckResult with pass/fail and evidence details.
    """
    must_include = [str(x) for x in spec.get("must_include", [])]
    must_include_any = [str(x) for x in spec.get("must_include_any", [])]
    source_type = str(spec.get("type", "")).strip()
    extract_mode = str(spec.get("extract_mode", "auto"))
    ocr_mode = str(spec.get("ocr_mode", "dual"))
    location_hints = [str(x) for x in spec.get("location_hints", []) if str(x).strip()]
    body = ""
    extraction_detail = ""

    try:
        if source_type == "url_text":
            body = fetch_url_text(
                str(spec["url"]),
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        elif source_type == "remote_pdf":
            body = fetch_remote_pdf_text(
                str(spec["url"]),
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        elif source_type in {"local_pdf", "local_docx", "local_pptx", "local_image"}:
            path = Path(str(spec["path"]))
            extracted = extract_local_source_text(
                source_type=source_type,
                path=path,
                extract_mode=extract_mode,
                ocr_mode=ocr_mode,
                location_hints=location_hints,
            )
            body = extracted.text
            extraction_detail = extracted.detail
        else:
            return GateCheckResult(
                source_id=source_id,
                tier=tier,
                ok=False,
                reachable=False,
                matched_tokens=0,
                total_tokens=len(must_include) + (1 if must_include_any else 0),
                detail=f"Unsupported source type: {source_type}",
            )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError, FileNotFoundError) as exc:
        return GateCheckResult(
            source_id=source_id,
            tier=tier,
            ok=False,
            reachable=False,
            matched_tokens=0,
            total_tokens=len(must_include) + (1 if must_include_any else 0),
            detail=f"Fetch/parse failed: {exc}",
        )

    normalized_body = _normalize_for_match(body)
    missing_tokens = [tok for tok in must_include if _normalize_for_match(tok) not in normalized_body]
    matched_required = len(must_include) - len(missing_tokens)

    matched_any = 0
    missing_any: List[str] = []
    if must_include_any:
        any_matches = [tok for tok in must_include_any if _normalize_for_match(tok) in normalized_body]
        if any_matches:
            matched_any = 1
        else:
            missing_any = must_include_any

    total_tokens = len(must_include) + (1 if must_include_any else 0)
    matched = matched_required + matched_any
    ok = matched_required == len(must_include) and (not must_include_any or matched_any == 1)
    detail_parts: List[str] = []
    if missing_tokens:
        detail_parts.append("missing evidence tokens: " + "; ".join(missing_tokens[:3]))
    if missing_any:
        detail_parts.append("must_include_any not matched: " + "; ".join(missing_any[:3]))
    if not detail_parts:
        detail_parts.append("all tokens matched")
    if extraction_detail:
        detail_parts.append(f"extractor={extraction_detail}")

    return GateCheckResult(
        source_id=source_id,
        tier=tier,
        ok=ok,
        reachable=True,
        matched_tokens=matched,
        total_tokens=total_tokens,
        detail="; ".join(detail_parts),
        evidence_excerpt=_make_excerpt(body),
        extraction_detail=extraction_detail,
    )


def run_evidence_gate(
    sources_config: Dict[str, Any],
    ca_bundle: Optional[str] = None,
    allow_insecure_tls: bool = False,
) -> Dict[str, Any]:
    """Run evidence gate on all configured sources.

    Args:
        sources_config: Dict with 'required_sources' and 'optional_sources'.
        ca_bundle: Optional CA bundle path.
        allow_insecure_tls: Disable TLS verification (diagnostic only).

    Returns:
        Gate result dict: all_required_passed, required_failed_count, results.
    """
    required = sources_config.get("required_sources", {})
    optional = sources_config.get("optional_sources", {})
    if not isinstance(required, dict) or not isinstance(optional, dict):
        raise ValueError("required_sources and optional_sources must be objects")
    if len(required) == 0:
        return {
            "all_required_passed": False,
            "required_failed_count": 1,
            "config_error": "required_sources is empty; configure at least one required source",
            "results": [],
        }

    results: List[GateCheckResult] = []
    for source_id, spec in required.items():
        results.append(
            check_one_source(
                source_id,
                spec,
                "required",
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        )
    for source_id, spec in optional.items():
        results.append(
            check_one_source(
                source_id,
                spec,
                "optional",
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        )

    required_failed = [r for r in results if r.tier == "required" and not r.ok]
    return {
        "all_required_passed": len(required_failed) == 0,
        "required_failed_count": len(required_failed),
        "results": [
            {
                "source_id": r.source_id,
                "tier": r.tier,
                "ok": r.ok,
                "reachable": r.reachable,
                "matched_tokens": r.matched_tokens,
                "total_tokens": r.total_tokens,
                "detail": r.detail,
                "evidence_excerpt": r.evidence_excerpt,
                "extraction_detail": r.extraction_detail,
            }
            for r in results
        ],
    }

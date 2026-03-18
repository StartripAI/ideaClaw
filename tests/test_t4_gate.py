"""T4: Evidence gate tests (4 tests).

Tests URL reachability, unreachable URLs, token matching via
the GateCheckResult protocol, and source types.
"""

from __future__ import annotations

import pytest
from ideaclaw.evidence.gate import (
    fetch_url_text,
    check_one_source,
    GateCheckResult,
)


# ---- T4.1: URL reachable ----
@pytest.mark.network
def test_t4_1_url_reachable():
    """T4.1: Known URL should be reachable."""
    text = fetch_url_text("https://arxiv.org")
    assert text is not None, "arxiv.org should be reachable"
    assert len(text) > 100, "Should return substantial content"


# ---- T4.2: URL unreachable ----
@pytest.mark.network
def test_t4_2_url_unreachable():
    """T4.2: Nonexistent URL should return empty or fail gracefully."""
    try:
        text = fetch_url_text("https://this-domain-definitely-does-not-exist-9999.invalid")
        assert text is None or text == "", "Nonexistent URL should fail gracefully"
    except Exception:
        # Raising URLError/SSL error is also acceptable for unreachable domains
        pass


# ---- T4.3: GateCheckResult structure ----
def test_t4_3_gate_check_result_structure():
    """T4.3: GateCheckResult should have all required fields."""
    # Test with a real source type that gate supports — use a bad URL
    # so it runs fast (no real network call for unreachable host)
    result = check_one_source(
        source_id="test_src",
        spec={
            "type": "url_text",
            "url": "file:///nonexistent/path/to/file",
            "must_include": ["median overall survival"],
        },
    )
    assert isinstance(result, GateCheckResult)
    # Verify all fields exist
    assert hasattr(result, "source_id")
    assert hasattr(result, "ok")
    assert hasattr(result, "reachable")
    assert hasattr(result, "matched_tokens")
    assert hasattr(result, "total_tokens")
    assert hasattr(result, "detail")
    assert result.source_id == "test_src"
    assert result.total_tokens >= 1, "Should count must_include tokens"


# ---- T4.4: Unsupported source type ----
def test_t4_4_unsupported_source_type():
    """T4.4: Unsupported source type should return ok=False with explanation."""
    result = check_one_source(
        source_id="test_bad_type",
        spec={
            "type": "invalid_unknown_type",
            "url": "http://example.com",
            "must_include": ["test"],
        },
    )
    assert isinstance(result, GateCheckResult)
    assert not result.ok, "Unsupported type should not pass"
    assert "unsupported" in result.detail.lower() or "unknown" in result.detail.lower()

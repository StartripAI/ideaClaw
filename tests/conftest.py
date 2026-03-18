"""Pytest configuration and shared fixtures for IdeaClaw tests."""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after test."""
    with tempfile.TemporaryDirectory(prefix="ideaclaw_test_") as d:
        yield Path(d)


@pytest.fixture
def sample_markdown():
    """Sample markdown content for export tests."""
    return (
        "# Introduction\n"
        "This is a **test** paper about transformer efficiency.\n\n"
        "## Methods\n"
        "- Step 1: collect data\n"
        "- Step 2: run experiments\n\n"
        "| Model | Acc | Speed |\n"
        "|---|---|---|\n"
        "| GPT | 92% | fast |\n"
        "| BERT | 89% | slow |\n"
    )


# Markers for tests that require network access
def pytest_configure(config):
    config.addinivalue_line("markers", "network: tests that require network access (live API calls)")
    config.addinivalue_line("markers", "slow: tests that take >5 seconds")

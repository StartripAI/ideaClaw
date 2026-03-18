"""Configuration loader for IdeaClaw."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

# Default config values (used when no config file is provided)
DEFAULTS: Dict[str, Any] = {
    "project": {"name": "ideaclaw-run"},
    "idea": {"text": "", "pack_type": "auto", "language": "en"},
    "runtime": {"timezone": "UTC", "retry_limit": 2, "approval_timeout_hours": 12},
    "llm": {
        "provider": "openai-compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "api_key": "",
        "primary_model": "gpt-4o",
        "fallback_models": ["gpt-4o-mini"],
    },
    "source": {
        "search_engines": ["google", "bing"],
        "academic_apis": ["openalex", "semantic_scholar"],
        "local_paths": [],
        "quality_threshold": 4.0,
        "daily_source_count": 10,
    },
    "evidence": {
        "profile": "fulltext-preferred",
        "gate_mode": "strict",
        "ocr_mode": "auto",
    },
    "export": {
        "formats": ["markdown", "docx"],
        "include_audit": True,
        "include_sources": True,
    },
    "security": {
        "hitl_required_stages": [5, 7, 14],
        "auto_approve": False,
    },
    "prompts": {"custom_file": ""},
    "notifications": {"channel": "console", "target": ""},
    "knowledge_base": {"backend": "markdown", "root": "docs/kb"},
}


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override into base, preferring override values."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load configuration from YAML file, merged with defaults.

    Args:
        config_path: Path to config YAML. If None, uses defaults only.

    Returns:
        Merged configuration dictionary.
    """
    config = dict(DEFAULTS)

    if config_path is not None:
        resolved = Path(config_path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Config file not found: {resolved}")
        with open(resolved, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, user_config)

    return config

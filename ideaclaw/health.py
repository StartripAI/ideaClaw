"""IdeaClaw health check — doctor report system.

Ported from ARC's health.py with enhancements:
  - 12 diagnostic checks (vs ARC's 8)
  - Actionable fix suggestions for each failure
  - DoctorReport with markdown and JSON output
  - Checks: Python version, YAML, config validity, LLM connectivity,
    network, disk space, dependencies, orchestrator profiles, etc.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckResult:
    """Result of a single health check."""
    name: str
    status: str          # "pass" | "fail" | "warn"
    detail: str
    fix: str = ""


@dataclass
class DoctorReport:
    """Aggregate health report."""
    timestamp: str = ""
    checks: List[CheckResult] = field(default_factory=list)
    overall: str = "unknown"    # healthy | degraded | unhealthy

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def warned(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def actionable_fixes(self) -> List[str]:
        return [c.fix for c in self.checks if c.fix]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall": self.overall,
            "summary": {"pass": self.passed, "fail": self.failed, "warn": self.warned},
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail, "fix": c.fix}
                for c in self.checks
            ],
            "actionable_fixes": self.actionable_fixes,
        }

    def to_markdown(self) -> str:
        icon_map = {"pass": "✅", "fail": "❌", "warn": "⚠️"}
        overall_icon = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌"}.get(self.overall, "❓")
        lines = [
            f"# IdeaClaw Health Report {overall_icon}",
            f"**Status**: {self.overall} | ✅ {self.passed} pass | ❌ {self.failed} fail | ⚠️ {self.warned} warn",
            f"**Time**: {self.timestamp}",
            "",
            "| Check | Status | Detail | Fix |",
            "|---|---|---|---|",
        ]
        for c in self.checks:
            icon = icon_map.get(c.status, "?")
            fix_text = c.fix if c.fix else "—"
            lines.append(f"| {c.name} | {icon} | {c.detail} | {fix_text} |")

        if self.actionable_fixes:
            lines.extend(["", "## Suggested Fixes", ""])
            for i, fix in enumerate(self.actionable_fixes, 1):
                lines.append(f"{i}. {fix}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_python_version() -> CheckResult:
    """Check Python version (≥ 3.10 required)."""
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 10):
        return CheckResult("python_version", "pass", f"Python {version_str}")
    return CheckResult(
        "python_version", "fail", f"Python {version_str} too old",
        fix="Install Python 3.10 or newer",
    )


def check_yaml_import() -> CheckResult:
    """Check PyYAML is available."""
    try:
        importlib.import_module("yaml")
        return CheckResult("yaml_import", "pass", "PyYAML available")
    except ImportError:
        return CheckResult("yaml_import", "fail", "PyYAML not found", fix="pip install pyyaml")


def check_config_valid(config_path: Optional[str] = None) -> CheckResult:
    """Validate configuration file."""
    from ideaclaw.config import resolve_config_path, validate_config

    path = resolve_config_path(config_path)
    if path is None or not path.exists():
        return CheckResult(
            "config_valid", "warn",
            "No config file found (using defaults)",
            fix="Create config.ideaclaw.yaml",
        )

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        return CheckResult("config_valid", "fail", f"YAML parse error: {e}",
                           fix="Fix YAML syntax in config file")
    except OSError as e:
        return CheckResult("config_valid", "fail", f"Cannot read: {e}",
                           fix="Check file permissions")

    if not isinstance(data, dict):
        return CheckResult("config_valid", "fail", "Config root must be a mapping")

    result = validate_config(data)
    if result.ok:
        return CheckResult("config_valid", "pass", "Config valid")
    return CheckResult(
        "config_valid", "fail",
        "; ".join(result.errors),
        fix="Fix config validation errors",
    )


def check_llm_connectivity(config_path: Optional[str] = None) -> CheckResult:
    """Check LLM API is reachable."""
    from ideaclaw.config import load_config, resolve_config_path

    try:
        path = resolve_config_path(config_path)
        cfg = load_config(path)
        base_url = cfg.llm.base_url
    except Exception:
        base_url = "https://api.openai.com/v1"

    if not base_url:
        return CheckResult("llm_connectivity", "warn", "No LLM base_url configured")

    models_url = f"{base_url.rstrip('/')}/models"
    try:
        req = urllib.request.Request(models_url, headers={"User-Agent": "IdeaClaw/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return CheckResult("llm_connectivity", "pass", f"LLM API reachable ({base_url})")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return CheckResult("llm_connectivity", "warn",
                               f"LLM API reachable but auth required ({e.code})",
                               fix="Set LLM API key via env variable or config")
        return CheckResult("llm_connectivity", "fail", f"LLM API HTTP {e.code}")
    except Exception as e:
        return CheckResult("llm_connectivity", "fail", f"Cannot reach LLM: {e}",
                           fix="Check LLM base_url and network connectivity")

    return CheckResult("llm_connectivity", "fail", "LLM unreachable")


def check_network() -> CheckResult:
    """Check basic internet connectivity."""
    targets = [
        ("api.openalex.org", 443),
        ("api.semanticscholar.org", 443),
        ("export.arxiv.org", 443),
    ]
    ok = 0
    for host, port in targets:
        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
            ok += 1
        except Exception:
            pass

    if ok == len(targets):
        return CheckResult("network", "pass", f"All {ok} APIs reachable")
    elif ok > 0:
        return CheckResult("network", "warn", f"{ok}/{len(targets)} APIs reachable")
    return CheckResult("network", "fail", "No APIs reachable",
                       fix="Check internet connection")


def check_disk_space() -> CheckResult:
    """Check available disk space (≥1GB recommended)."""
    try:
        usage = shutil.disk_usage(Path.home())
        free_gb = usage.free / (1024 ** 3)
        if free_gb >= 1.0:
            return CheckResult("disk_space", "pass", f"{free_gb:.1f} GB free")
        elif free_gb >= 0.5:
            return CheckResult("disk_space", "warn", f"Low disk: {free_gb:.1f} GB free")
        return CheckResult("disk_space", "fail", f"Very low: {free_gb:.1f} GB free",
                           fix="Free up disk space")
    except Exception as e:
        return CheckResult("disk_space", "warn", f"Cannot check: {e}")


def check_dependencies() -> CheckResult:
    """Check optional dependencies."""
    deps = {
        "pyyaml": "yaml",
        "sentence-transformers": "sentence_transformers",
        "matplotlib": "matplotlib",
        "docx": "docx",
    }
    missing = []
    found = []
    for pretty, module in deps.items():
        try:
            importlib.import_module(module)
            found.append(pretty)
        except ImportError:
            missing.append(pretty)

    if not missing:
        return CheckResult("dependencies", "pass", f"All {len(found)} optional deps found")
    elif len(missing) <= 2:
        return CheckResult("dependencies", "warn",
                           f"Missing optional: {', '.join(missing)}",
                           fix=f"pip install {' '.join(missing)}")
    return CheckResult("dependencies", "warn",
                       f"Missing {len(missing)} optional: {', '.join(missing)}",
                       fix=f"pip install {' '.join(missing)}")


def check_orchestrator_profiles() -> CheckResult:
    """Check that orchestrator profiles directory exists and has YAMLs."""
    profile_dirs = [
        Path(__file__).parent / "orchestrator" / "profiles",
        Path("orchestrator/profiles"),
    ]
    for pd in profile_dirs:
        if pd.exists():
            yamls = list(pd.glob("*.yaml"))
            if yamls:
                return CheckResult("orchestrator_profiles", "pass",
                                   f"{len(yamls)} scenario profiles in {pd}")
            return CheckResult("orchestrator_profiles", "warn",
                               f"Profile dir exists but empty: {pd}")

    return CheckResult("orchestrator_profiles", "warn",
                       "orchestrator/profiles/ not found",
                       fix="Ensure orchestrator/profiles/ directory exists")


def check_cache_dir() -> CheckResult:
    """Check cache directory is writable."""
    cache_dir = Path.home() / ".cache" / "ideaclaw"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        test_file = cache_dir / ".health_check"
        test_file.write_text("ok")
        test_file.unlink()
        return CheckResult("cache_dir", "pass", f"Cache writable: {cache_dir}")
    except Exception as e:
        return CheckResult("cache_dir", "fail", f"Cache not writable: {e}",
                           fix=f"Check permissions on {cache_dir}")


def check_api_keys() -> CheckResult:
    """Check if important API keys are set."""
    keys = {
        "OPENAI_API_KEY": "OpenAI",
        "ANTHROPIC_API_KEY": "Anthropic",
        "S2_API_KEY": "Semantic Scholar",
    }
    found = [name for env, name in keys.items() if os.environ.get(env)]
    if found:
        return CheckResult("api_keys", "pass", f"API keys found: {', '.join(found)}")
    return CheckResult("api_keys", "warn",
                       "No API keys found in environment",
                       fix="Set OPENAI_API_KEY or ANTHROPIC_API_KEY")


def check_git() -> CheckResult:
    """Check git is available (needed for versioning)."""
    git_path = shutil.which("git")
    if git_path:
        return CheckResult("git", "pass", f"git found: {git_path}")
    return CheckResult("git", "warn", "git not found",
                       fix="Install git for version control features")


# ---------------------------------------------------------------------------
# Doctor: run all checks
# ---------------------------------------------------------------------------

def run_doctor(config_path: Optional[str] = None) -> DoctorReport:
    """Run all health checks and produce a DoctorReport.

    Args:
        config_path: Optional explicit config file path.

    Returns:
        DoctorReport with all check results.
    """
    report = DoctorReport(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    # Run checks: fast → slow
    checks = [
        check_python_version,
        check_yaml_import,
        lambda: check_config_valid(config_path),
        check_disk_space,
        check_cache_dir,
        check_git,
        check_dependencies,
        check_api_keys,
        check_orchestrator_profiles,
        check_network,
        lambda: check_llm_connectivity(config_path),
    ]

    for check_fn in checks:
        try:
            result = check_fn()
            report.checks.append(result)
        except Exception as e:
            report.checks.append(CheckResult(
                name=check_fn.__name__ if hasattr(check_fn, '__name__') else "unknown",
                status="fail", detail=f"Check crashed: {e}",
            ))

    # Determine overall status
    if report.failed == 0 and report.warned == 0:
        report.overall = "healthy"
    elif report.failed == 0:
        report.overall = "degraded"
    else:
        report.overall = "unhealthy"

    return report

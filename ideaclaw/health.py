"""Environment and dependency health checks."""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

from rich.console import Console

console = Console()


def check_python_version() -> Tuple[bool, str]:
    """Check Python version >= 3.11."""
    version = sys.version_info
    ok = version >= (3, 11)
    msg = f"Python {version.major}.{version.minor}.{version.micro}"
    return ok, msg


def check_api_key(env_var: str = "OPENAI_API_KEY") -> Tuple[bool, str]:
    """Check if LLM API key is set."""
    key = os.environ.get(env_var, "")
    if key:
        return True, f"{env_var} is set (***{key[-4:]})"
    return False, f"{env_var} is not set"


def check_optional_dep(package: str) -> Tuple[bool, str]:
    """Check if an optional dependency is importable."""
    try:
        __import__(package)
        return True, f"{package} available"
    except ImportError:
        return False, f"{package} not installed (optional)"


def run_health_check(api_key_env: str = "OPENAI_API_KEY") -> bool:
    """Run all health checks and print results. Returns True if all required checks pass."""
    checks: List[Tuple[str, bool, str, bool]] = []  # (name, passed, msg, required)

    ok, msg = check_python_version()
    checks.append(("Python ≥ 3.11", ok, msg, True))

    ok, msg = check_api_key(api_key_env)
    checks.append(("LLM API Key", ok, msg, True))

    for pkg in ["yaml", "rich", "jinja2"]:
        ok, msg = check_optional_dep(pkg)
        checks.append((f"Package: {pkg}", ok, msg, True))

    for pkg in ["docx", "weasyprint", "paddleocr", "easyocr"]:
        ok, msg = check_optional_dep(pkg)
        checks.append((f"Package: {pkg}", ok, msg, False))

    all_required_ok = True
    for name, passed, msg, required in checks:
        icon = "✅" if passed else ("❌" if required else "⚠️")
        tag = "[required]" if required else "[optional]"
        console.print(f"  {icon} {name}: {msg} {tag}")
        if required and not passed:
            all_required_ok = False

    return all_required_ok

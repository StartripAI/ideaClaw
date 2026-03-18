"""Run artifact management — ported from OpenRevise run_artifact_utils.py."""

from __future__ import annotations

import datetime as dt
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def utc_now() -> dt.datetime:
    """Current UTC datetime."""
    return dt.datetime.now(dt.timezone.utc)


def to_iso_z(d: dt.datetime) -> str:
    """Format datetime as ISO 8601 with Z suffix."""
    return d.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_run_id() -> str:
    """Generate a unique run ID."""
    now = utc_now()
    ts = now.strftime("%Y%m%d-%H%M%S")
    h = hashlib.sha256(f"{ts}-{id(now)}".encode()).hexdigest()[:8]
    return f"ic-{ts}-{h}"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_copy2(src: Path, dst: Path) -> Path:
    """Copy file, creating parent dirs as needed."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def ensure_run_layout(run_dir: Path) -> None:
    """Create standard subdirectories for a run."""
    for subdir in ["evidence", "evidence/extracted", "reasoning", "trust", "export"]:
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)


@dataclass
class ArtifactRecord:
    """Metadata for a run artifact."""
    artifact_type: str
    path: Path
    hash: str
    size: int
    phase: str
    retention_tier: str = "PERMANENT"

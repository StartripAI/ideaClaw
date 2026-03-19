"""I/O utilities — TSV, JSON, YAML helpers."""

from __future__ import annotations
import logging

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

__all__ = ['write_json', 'read_json', 'write_tsv', 'read_tsv']


def write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    """Write data as JSON with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    """Read JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_tsv(path: Path, fields: List[str], rows: List[Dict[str, str]]) -> None:
    """Write rows as a TSV file with header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path: Path) -> List[Dict[str, str]]:
    """Read TSV file into list of dicts."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)

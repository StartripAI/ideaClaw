"""Hashing utilities."""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_string(text: str) -> str:
    """Compute SHA-256 hash of a string."""
    return sha256_bytes(text.encode("utf-8"))

"""Shared utilities for AutoBassTab."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def ensure_dir(path: Path) -> Path:
    """Create directory if it doesn't exist and return it.

    Args:
        path: Directory path to ensure exists.

    Returns:
        The same path, guaranteed to exist.
    """
    path.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured directory exists: {}", path)
    return path

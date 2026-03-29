"""Module 2: Audio source separation using Demucs."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.models import SeparationConfig, SeparationError


def separate_bass(config: SeparationConfig) -> Path:
    """Separate bass track from a full audio mix using Demucs.

    Args:
        config: Separation configuration with input path and model settings.

    Returns:
        Path to the isolated bass audio file (bass_only.wav).

    Raises:
        SeparationError: If demucs is not installed or separation fails.
    """
    try:
        import demucs  # noqa: F401
    except ImportError as e:
        raise SeparationError(
            "demucs is not installed. "
            "Install with: pip install autobass[pipeline]"
        ) from e

    if not config.input_path.exists():
        raise SeparationError(f"Input file not found: {config.input_path}")

    logger.info("Separating bass from: {}", config.input_path)
    output_path = config.output_dir / "bass_only.wav"
    config.output_dir.mkdir(parents=True, exist_ok=True)

    raise NotImplementedError(
        "separate_bass() is a stub. "
        "Use /implement separate_bass to generate the full implementation."
    )

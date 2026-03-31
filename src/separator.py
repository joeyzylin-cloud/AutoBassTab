"""Module 2: Audio source separation using Demucs."""

from __future__ import annotations

import shutil
import subprocess
import sys
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
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Run demucs as subprocess — it writes to separated/<model>/<track>/bass.wav
    try:
        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems", "bass",
            "-n", config.model_name,
            "-o", str(config.output_dir / "separated"),
            str(config.input_path),
        ]
        logger.info("Running: {}", " ".join(cmd))
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise SeparationError(f"Demucs failed: {e.stderr}") from e

    # Locate the bass output from demucs
    stem_name = config.input_path.stem
    demucs_bass = config.output_dir / "separated" / config.model_name / stem_name / "bass.wav"

    if not demucs_bass.exists():
        raise SeparationError(
            f"Demucs completed but bass file not found at: {demucs_bass}"
        )

    # Copy to our standard output path
    output_path = config.output_dir / "bass_only.wav"
    shutil.copy2(demucs_bass, output_path)

    logger.info("Bass track saved to: {} ({:.1f} MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path

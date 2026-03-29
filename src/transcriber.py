"""Module 3: Pitch transcription using basic-pitch."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.models import TranscribeConfig, TranscribeError


def transcribe_to_midi(config: TranscribeConfig) -> Path:
    """Transcribe an audio file to MIDI using basic-pitch.

    Args:
        config: Transcription configuration with input path and output settings.

    Returns:
        Path to the generated MIDI file (bass_track.mid).

    Raises:
        TranscribeError: If basic-pitch is not installed or transcription fails.
    """
    try:
        import basic_pitch  # noqa: F401
    except ImportError as e:
        raise TranscribeError(
            "basic-pitch is not installed. "
            "Install with: pip install autobass[pipeline]"
        ) from e

    if not config.input_path.exists():
        raise TranscribeError(f"Input file not found: {config.input_path}")

    logger.info("Transcribing audio to MIDI: {}", config.input_path)
    output_path = config.output_dir / "bass_track.mid"
    config.output_dir.mkdir(parents=True, exist_ok=True)

    raise NotImplementedError(
        "transcribe_to_midi() is a stub. "
        "Use /implement transcribe_to_midi to generate the full implementation."
    )

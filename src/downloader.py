"""Module 1: YouTube audio downloader using yt-dlp."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.models import DownloadConfig, DownloadError


def download_audio(config: DownloadConfig) -> Path:
    """Download audio from a YouTube URL and save as WAV.

    Args:
        config: Download configuration with URL and output settings.

    Returns:
        Path to the downloaded audio file (audio_full.wav).

    Raises:
        DownloadError: If yt-dlp is not installed or download fails.
    """
    try:
        import yt_dlp  # noqa: F401
    except ImportError as e:
        raise DownloadError(
            "yt-dlp is not installed. "
            "Install with: pip install autobass[pipeline]"
        ) from e

    logger.info("Downloading audio from: {}", config.url)
    output_path = config.output_dir / "audio_full.wav"
    config.output_dir.mkdir(parents=True, exist_ok=True)

    raise NotImplementedError(
        "download_audio() is a stub. "
        "Use /implement download_audio to generate the full implementation."
    )

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
        import yt_dlp
    except ImportError as e:
        raise DownloadError(
            "yt-dlp is not installed. "
            "Install with: pip install autobass[pipeline]"
        ) from e

    logger.info("Downloading audio from: {}", config.url)
    output_path = config.output_dir / "audio_full.wav"
    config.output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(config.output_dir / "audio_full.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": config.audio_format,
                "preferredquality": "0",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Extracting audio from YouTube...")
            ydl.download([config.url])
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(f"Failed to download: {e}") from e
    except Exception as e:
        raise DownloadError(f"Unexpected error during download: {e}") from e

    if not output_path.exists():
        raise DownloadError(
            f"Download completed but output file not found: {output_path}"
        )

    logger.info("Audio saved to: {} ({:.1f} MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path

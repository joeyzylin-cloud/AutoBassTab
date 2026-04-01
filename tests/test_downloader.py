"""Tests for the YouTube audio downloader module."""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from src.models import DownloadConfig, DownloadError


class TestDownloadAudio:
    """Tests for download_audio()."""

    def test_yt_dlp_not_installed(self, monkeypatch, tmp_path: Path) -> None:
        """Raises DownloadError when yt_dlp is not installed."""
        monkeypatch.setitem(sys.modules, "yt_dlp", None)
        # Re-import so the patched sys.modules takes effect
        if "src.downloader" in sys.modules:
            monkeypatch.delitem(sys.modules, "src.downloader")
        from src.downloader import download_audio
        config = DownloadConfig(url="https://youtu.be/test", output_dir=tmp_path)
        with pytest.raises(DownloadError, match="yt-dlp"):
            download_audio(config)

    def test_successful_download_returns_path(self, monkeypatch, tmp_path: Path) -> None:
        """Returns the path to audio_full.wav after a successful download."""
        # Build a minimal yt_dlp mock
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        mock_yt_dlp = ModuleType("yt_dlp")
        mock_yt_dlp.YoutubeDL = MagicMock(return_value=mock_ydl)
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = Exception
        monkeypatch.setitem(sys.modules, "yt_dlp", mock_yt_dlp)
        if "src.downloader" in sys.modules:
            monkeypatch.delitem(sys.modules, "src.downloader")

        # Pre-create the expected output file so the existence check passes
        output_file = tmp_path / "audio_full.wav"
        output_file.touch()

        from src.downloader import download_audio
        config = DownloadConfig(url="https://youtu.be/test", output_dir=tmp_path)
        result = download_audio(config)
        assert result == output_file

    def test_yt_dlp_download_error_raises(self, monkeypatch, tmp_path: Path) -> None:
        """Raises DownloadError when yt_dlp.utils.DownloadError is thrown."""
        class FakeDownloadError(Exception):
            pass

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.download.side_effect = FakeDownloadError("bad url")

        mock_yt_dlp = ModuleType("yt_dlp")
        mock_yt_dlp.YoutubeDL = MagicMock(return_value=mock_ydl)
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = FakeDownloadError
        monkeypatch.setitem(sys.modules, "yt_dlp", mock_yt_dlp)
        if "src.downloader" in sys.modules:
            monkeypatch.delitem(sys.modules, "src.downloader")

        from src.downloader import download_audio
        config = DownloadConfig(url="https://youtu.be/bad", output_dir=tmp_path)
        with pytest.raises(DownloadError, match="Failed to download"):
            download_audio(config)

    def test_unexpected_exception_raises(self, monkeypatch, tmp_path: Path) -> None:
        """Wraps unexpected exceptions in DownloadError."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.download.side_effect = RuntimeError("network gone")

        mock_yt_dlp = ModuleType("yt_dlp")
        mock_yt_dlp.YoutubeDL = MagicMock(return_value=mock_ydl)
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = type("NeverRaised", (Exception,), {})
        monkeypatch.setitem(sys.modules, "yt_dlp", mock_yt_dlp)
        if "src.downloader" in sys.modules:
            monkeypatch.delitem(sys.modules, "src.downloader")

        from src.downloader import download_audio
        config = DownloadConfig(url="https://youtu.be/test", output_dir=tmp_path)
        with pytest.raises(DownloadError, match="Unexpected error"):
            download_audio(config)

    def test_output_file_missing_raises(self, monkeypatch, tmp_path: Path) -> None:
        """Raises DownloadError when output file is absent after download completes."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        mock_yt_dlp = ModuleType("yt_dlp")
        mock_yt_dlp.YoutubeDL = MagicMock(return_value=mock_ydl)
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = Exception
        monkeypatch.setitem(sys.modules, "yt_dlp", mock_yt_dlp)
        if "src.downloader" in sys.modules:
            monkeypatch.delitem(sys.modules, "src.downloader")

        # Do NOT create the output file
        from src.downloader import download_audio
        config = DownloadConfig(url="https://youtu.be/test", output_dir=tmp_path)
        with pytest.raises(DownloadError, match="output file not found"):
            download_audio(config)

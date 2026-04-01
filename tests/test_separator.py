"""Tests for the audio source separation module."""

import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from src.models import SeparationConfig, SeparationError


def _make_demucs_mock(monkeypatch) -> None:
    """Insert a minimal demucs stub so the import check in separate_bass passes."""
    mock_demucs = ModuleType("demucs")
    monkeypatch.setitem(sys.modules, "demucs", mock_demucs)


def _reload_separator(monkeypatch) -> None:
    """Force re-import of src.separator so patched sys.modules is picked up."""
    if "src.separator" in sys.modules:
        monkeypatch.delitem(sys.modules, "src.separator")


class TestSeparateBass:
    """Tests for separate_bass()."""

    def test_demucs_not_installed(self, monkeypatch, tmp_path: Path) -> None:
        """Raises SeparationError when demucs is not installed."""
        monkeypatch.setitem(sys.modules, "demucs", None)
        _reload_separator(monkeypatch)
        from src.separator import separate_bass
        input_wav = tmp_path / "audio.wav"
        input_wav.touch()
        config = SeparationConfig(input_path=input_wav, output_dir=tmp_path)
        with pytest.raises(SeparationError, match="demucs"):
            separate_bass(config)

    def test_input_file_not_found(self, monkeypatch, tmp_path: Path) -> None:
        """Raises SeparationError when input file does not exist."""
        _make_demucs_mock(monkeypatch)
        _reload_separator(monkeypatch)
        from src.separator import separate_bass
        config = SeparationConfig(
            input_path=tmp_path / "nonexistent.wav",
            output_dir=tmp_path,
        )
        with pytest.raises(SeparationError, match="Input file not found"):
            separate_bass(config)

    def test_subprocess_failure_raises(self, monkeypatch, tmp_path: Path) -> None:
        """Raises SeparationError when Demucs subprocess returns non-zero."""
        _make_demucs_mock(monkeypatch)
        _reload_separator(monkeypatch)
        monkeypatch.setattr(
            "subprocess.run",
            MagicMock(side_effect=subprocess.CalledProcessError(1, "demucs", stderr="error")),
        )
        from src.separator import separate_bass
        input_wav = tmp_path / "audio.wav"
        input_wav.touch()
        config = SeparationConfig(input_path=input_wav, output_dir=tmp_path)
        with pytest.raises(SeparationError, match="Demucs failed"):
            separate_bass(config)

    def test_bass_wav_missing_after_run(self, monkeypatch, tmp_path: Path) -> None:
        """Raises SeparationError when bass.wav is absent after subprocess succeeds."""
        _make_demucs_mock(monkeypatch)
        _reload_separator(monkeypatch)
        monkeypatch.setattr("subprocess.run", MagicMock())
        from src.separator import separate_bass
        input_wav = tmp_path / "audio.wav"
        input_wav.touch()
        config = SeparationConfig(input_path=input_wav, output_dir=tmp_path)
        with pytest.raises(SeparationError, match="bass file not found"):
            separate_bass(config)

    def test_successful_separation_returns_path(self, monkeypatch, tmp_path: Path) -> None:
        """Returns path to bass_only.wav after successful separation."""
        _make_demucs_mock(monkeypatch)
        _reload_separator(monkeypatch)
        monkeypatch.setattr("subprocess.run", MagicMock())
        from src.separator import separate_bass

        input_wav = tmp_path / "audio.wav"
        input_wav.touch()

        # Create the demucs output structure that separate_bass expects
        stem_name = input_wav.stem  # "audio"
        demucs_bass = tmp_path / "separated" / "htdemucs" / stem_name / "bass.wav"
        demucs_bass.parent.mkdir(parents=True, exist_ok=True)
        demucs_bass.write_bytes(b"RIFF")  # minimal fake WAV content

        config = SeparationConfig(input_path=input_wav, output_dir=tmp_path)
        result = separate_bass(config)
        assert result == tmp_path / "bass_only.wav"
        assert result.exists()

    def test_custom_model_name_passed_to_subprocess(self, monkeypatch, tmp_path: Path) -> None:
        """The model name appears in the subprocess command arguments."""
        _make_demucs_mock(monkeypatch)
        _reload_separator(monkeypatch)

        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)

        monkeypatch.setattr("subprocess.run", fake_run)
        from src.separator import separate_bass

        input_wav = tmp_path / "audio.wav"
        input_wav.touch()

        # Pre-create output so the file-existence check passes
        demucs_bass = tmp_path / "separated" / "mdx_extra" / "audio" / "bass.wav"
        demucs_bass.parent.mkdir(parents=True, exist_ok=True)
        demucs_bass.write_bytes(b"RIFF")

        config = SeparationConfig(
            input_path=input_wav,
            output_dir=tmp_path,
            model_name="mdx_extra",
        )
        separate_bass(config)

        assert "-n" in captured_cmd
        idx = captured_cmd.index("-n")
        assert captured_cmd[idx + 1] == "mdx_extra"

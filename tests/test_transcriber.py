"""Tests for the pitch transcription module."""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pretty_midi
import pytest

from src.models import TranscribeConfig, TranscribeError
from src.transcriber import _lowpass, _to_mono


# ===========================================================================
# Pure helper function tests (no mocking needed)
# ===========================================================================

class TestToMono:
    """Tests for _to_mono()."""

    def test_mono_array_unchanged(self) -> None:
        """1-D input is returned as-is."""
        audio = np.array([0.1, 0.2, 0.3])
        result = _to_mono(audio)
        np.testing.assert_array_equal(result, audio)

    def test_stereo_averaged_to_mono(self) -> None:
        """2-D (samples × channels) input is averaged across channels."""
        left = np.array([1.0, 2.0, 3.0])
        right = np.array([3.0, 4.0, 5.0])
        stereo = np.stack([left, right], axis=1)
        result = _to_mono(stereo)
        expected = np.array([2.0, 3.0, 4.0])
        np.testing.assert_allclose(result, expected)


class TestLowpassFilter:
    """Tests for _lowpass()."""

    def test_output_shape_preserved_mono(self) -> None:
        """Output shape matches input shape for mono audio."""
        audio = np.random.default_rng(0).standard_normal(4410)
        result = _lowpass(audio, sr=44100, cutoff_hz=500.0)
        assert result.shape == audio.shape

    def test_output_shape_preserved_stereo(self) -> None:
        """Output shape matches input shape for stereo audio."""
        audio = np.random.default_rng(0).standard_normal((4410, 2))
        result = _lowpass(audio, sr=44100, cutoff_hz=500.0)
        assert result.shape == audio.shape

    def test_high_frequency_attenuated(self) -> None:
        """A 2 kHz sine wave is attenuated after a 500 Hz cutoff filter."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False)
        audio = np.sin(2 * np.pi * 2000 * t).astype(np.float64)
        filtered = _lowpass(audio, sr=sr, cutoff_hz=500.0)
        assert np.sqrt(np.mean(filtered ** 2)) < np.sqrt(np.mean(audio ** 2)) * 0.1


# ===========================================================================
# transcribe_to_midi integration tests (mock basic_pitch)
# ===========================================================================

def _make_mock_midi() -> pretty_midi.PrettyMIDI:
    """Create a minimal PrettyMIDI object to serve as mock output."""
    mid = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=33)
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=40, start=0.0, end=0.5))
    mid.instruments.append(inst)
    return mid


def _patch_basic_pitch(monkeypatch) -> None:
    """Inject a basic_pitch stub that returns a minimal MIDI object."""
    mock_midi = _make_mock_midi()

    mock_bp_inference = ModuleType("basic_pitch.inference")
    mock_bp_inference.predict = MagicMock(return_value=(None, mock_midi, None))

    mock_bp = ModuleType("basic_pitch")
    mock_bp.inference = mock_bp_inference

    monkeypatch.setitem(sys.modules, "basic_pitch", mock_bp)
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", mock_bp_inference)


def _patch_soundfile(monkeypatch, audio: np.ndarray, sr: int = 44100) -> None:
    """Patch soundfile.read to return a fixed numpy array."""
    import soundfile as sf
    monkeypatch.setattr(sf, "read", MagicMock(return_value=(audio, sr)))


class TestTranscribeToMidi:
    """Tests for transcribe_to_midi()."""

    def test_input_not_found_raises(self, monkeypatch, tmp_path: Path) -> None:
        """Raises TranscribeError when input file does not exist."""
        _patch_basic_pitch(monkeypatch)
        from src.transcriber import transcribe_to_midi
        config = TranscribeConfig(
            input_path=tmp_path / "nonexistent.wav",
            output_dir=tmp_path,
        )
        with pytest.raises(TranscribeError, match="Input file not found"):
            transcribe_to_midi(config)

    def test_basic_pitch_not_installed(self, monkeypatch, tmp_path: Path) -> None:
        """Raises TranscribeError when basic_pitch is not importable."""
        monkeypatch.setitem(sys.modules, "basic_pitch", None)
        monkeypatch.setitem(sys.modules, "basic_pitch.inference", None)
        if "src.transcriber" in sys.modules:
            monkeypatch.delitem(sys.modules, "src.transcriber")
        from src.transcriber import transcribe_to_midi
        input_wav = tmp_path / "bass.wav"
        input_wav.touch()
        config = TranscribeConfig(input_path=input_wav, output_dir=tmp_path)
        with pytest.raises(TranscribeError, match="basic-pitch"):
            transcribe_to_midi(config)

    def test_ducking_skipped_when_no_bass_path_is_none(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Pipeline runs without error when no_bass_path is None (ducking skipped)."""
        _patch_basic_pitch(monkeypatch)
        audio = np.zeros(4410, dtype=np.float32)
        _patch_soundfile(monkeypatch, audio)

        input_wav = tmp_path / "bass.wav"
        input_wav.touch()

        from src.transcriber import transcribe_to_midi
        config = TranscribeConfig(
            input_path=input_wav,
            output_dir=tmp_path,
            no_bass_path=None,
            octave_shift=0,  # simplify: skip librosa shift
        )
        result = transcribe_to_midi(config)
        assert result == tmp_path / "bass_track.mid"

    def test_octave_shift_zero_writes_filtered_wav(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """When octave_shift=0, writes bass_filtered.wav instead of bass_shifted.wav."""
        _patch_basic_pitch(monkeypatch)
        audio = np.zeros(4410, dtype=np.float32)
        _patch_soundfile(monkeypatch, audio)

        input_wav = tmp_path / "bass.wav"
        input_wav.touch()

        from src.transcriber import transcribe_to_midi
        config = TranscribeConfig(
            input_path=input_wav,
            output_dir=tmp_path,
            no_bass_path=None,
            octave_shift=0,
        )
        transcribe_to_midi(config)

        assert (tmp_path / "bass_filtered.wav").exists()
        assert not (tmp_path / "bass_shifted.wav").exists()

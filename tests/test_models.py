"""Tests for data models."""

from pathlib import Path

import pytest

from src.models import (
    AssignedNote,
    BassConfig,
    DownloadConfig,
    DownloadError,
    FretPosition,
    NoteEvent,
    SeparationConfig,
    SeparationError,
    Strategy,
    TabConfig,
    TabEngineError,
    TranscribeConfig,
    TranscribeError,
)


class TestFretPosition:
    """Tests for FretPosition validation."""

    def test_valid_position(self) -> None:
        pos = FretPosition(string_number=1, fret=5)
        assert pos.string_number == 1
        assert pos.fret == 5

    def test_open_string(self) -> None:
        pos = FretPosition(string_number=4, fret=0)
        assert pos.fret == 0

    def test_max_fret(self) -> None:
        pos = FretPosition(string_number=1, fret=24)
        assert pos.fret == 24

    def test_string_number_too_low(self) -> None:
        with pytest.raises(ValueError, match="string_number must be 1-5"):
            FretPosition(string_number=0, fret=5)

    def test_string_5_valid(self) -> None:
        pos = FretPosition(string_number=5, fret=0)
        assert pos.string_number == 5

    def test_string_number_too_high(self) -> None:
        with pytest.raises(ValueError, match="string_number must be 1-5"):
            FretPosition(string_number=6, fret=5)

    def test_fret_negative(self) -> None:
        with pytest.raises(ValueError, match="fret must be 0-24"):
            FretPosition(string_number=1, fret=-1)

    def test_fret_too_high(self) -> None:
        with pytest.raises(ValueError, match="fret must be 0-24"):
            FretPosition(string_number=1, fret=25)


class TestBassConfigMidiToPositions:
    """Tests for BassConfig.midi_to_positions()."""

    def setup_method(self) -> None:
        self.bass = BassConfig()

    def test_open_e_string(self) -> None:
        """MIDI 28 = open E (or B string fret 5)."""
        positions = self.bass.midi_to_positions(28)
        assert FretPosition(string_number=4, fret=0) in positions
        assert FretPosition(string_number=5, fret=5) in positions

    def test_open_a_string(self) -> None:
        """MIDI 33 = open A, E fret 5, B fret 10."""
        positions = self.bass.midi_to_positions(33)
        assert FretPosition(string_number=3, fret=0) in positions
        assert FretPosition(string_number=4, fret=5) in positions
        assert FretPosition(string_number=5, fret=10) in positions

    def test_multiple_positions_e2(self) -> None:
        """MIDI 40 (E2) should have positions on all 5 strings."""
        positions = self.bass.midi_to_positions(40)
        expected = [
            FretPosition(string_number=2, fret=2),    # D string
            FretPosition(string_number=3, fret=7),    # A string
            FretPosition(string_number=4, fret=12),   # E string
            FretPosition(string_number=5, fret=17),   # B string
        ]
        assert positions == expected

    def test_open_b_string(self) -> None:
        """MIDI 23 = open B string only."""
        positions = self.bass.midi_to_positions(23)
        assert positions == [FretPosition(string_number=5, fret=0)]

    def test_sorted_by_fret_then_string(self) -> None:
        """Positions should be sorted by (fret, string_number)."""
        positions = self.bass.midi_to_positions(43)  # open G
        # fret=0 on G(1), fret=5 on D(2), fret=10 on A(3), fret=15 on E(4)
        assert positions[0].fret <= positions[-1].fret

    def test_out_of_range_too_low(self) -> None:
        """MIDI 22 is below the lowest note (B string open = 23)."""
        positions = self.bass.midi_to_positions(22)
        assert positions == []

    def test_out_of_range_too_high(self) -> None:
        """MIDI 68 = G string fret 25, out of range."""
        positions = self.bass.midi_to_positions(68)
        assert positions == []

    def test_highest_playable_note(self) -> None:
        """MIDI 67 = G string fret 24, the highest playable note."""
        positions = self.bass.midi_to_positions(67)
        assert FretPosition(string_number=1, fret=24) in positions


class TestStrategy:
    """Tests for Strategy enum."""

    def test_all_values(self) -> None:
        assert Strategy.LOWEST_POSITION.value == "lowest_position"
        assert Strategy.MIN_MOVEMENT.value == "min_movement"
        assert Strategy.OPEN_STRING_PREFER.value == "open_string_prefer"


# ===========================================================================
# NoteEvent tests
# ===========================================================================

class TestNoteEvent:
    """Tests for NoteEvent dataclass."""

    def test_basic_construction(self) -> None:
        """NoteEvent stores all fields correctly."""
        note = NoteEvent(midi_pitch=40, start_time=0.0, end_time=0.5, velocity=80)
        assert note.midi_pitch == 40
        assert note.start_time == 0.0
        assert note.end_time == 0.5
        assert note.velocity == 80

    def test_default_velocity(self) -> None:
        """Velocity defaults to 100 when not supplied."""
        note = NoteEvent(midi_pitch=33, start_time=1.0, end_time=1.5)
        assert note.velocity == 100

    def test_duration(self) -> None:
        """end_time - start_time gives note duration."""
        note = NoteEvent(midi_pitch=28, start_time=0.25, end_time=0.75)
        assert abs((note.end_time - note.start_time) - 0.5) < 1e-9


# ===========================================================================
# AssignedNote tests
# ===========================================================================

class TestAssignedNote:
    """Tests for AssignedNote dataclass."""

    def test_basic_construction(self) -> None:
        """AssignedNote stores event and position."""
        event = NoteEvent(midi_pitch=40, start_time=0.0, end_time=0.5)
        position = FretPosition(string_number=2, fret=2)
        assigned = AssignedNote(event=event, position=position)
        assert assigned.event == event
        assert assigned.position == position


# ===========================================================================
# Config dataclass tests
# ===========================================================================

class TestConfigDataclasses:
    """Tests for configuration dataclasses."""

    def test_download_config_defaults(self, tmp_path: Path) -> None:
        """DownloadConfig sets audio_format to 'wav' by default."""
        cfg = DownloadConfig(url="https://youtu.be/test", output_dir=tmp_path)
        assert cfg.audio_format == "wav"
        assert cfg.url == "https://youtu.be/test"

    def test_separation_config_default_model(self, tmp_path: Path) -> None:
        """SeparationConfig defaults to htdemucs model."""
        cfg = SeparationConfig(input_path=tmp_path / "audio.wav", output_dir=tmp_path)
        assert cfg.model_name == "htdemucs"

    def test_transcribe_config_defaults(self, tmp_path: Path) -> None:
        """TranscribeConfig has correct default thresholds and octave_shift."""
        cfg = TranscribeConfig(input_path=tmp_path / "bass.wav", output_dir=tmp_path)
        assert cfg.onset_threshold == 0.5
        assert cfg.frame_threshold == 0.4
        assert cfg.octave_shift == 12
        assert cfg.no_bass_path is None

    def test_tab_config_default_strategy(self, tmp_path: Path) -> None:
        """TabConfig defaults to LOWEST_POSITION strategy."""
        cfg = TabConfig(input_path=tmp_path / "bass.mid", output_dir=tmp_path)
        assert cfg.strategy == Strategy.LOWEST_POSITION


# ===========================================================================
# Custom exception tests
# ===========================================================================

class TestCustomExceptions:
    """Tests for custom exception classes."""

    def test_download_error_is_exception(self) -> None:
        """DownloadError is an Exception subclass with a message."""
        err = DownloadError("download failed")
        assert isinstance(err, Exception)
        assert str(err) == "download failed"

    def test_separation_error(self) -> None:
        """SeparationError is an Exception subclass."""
        assert isinstance(SeparationError("sep failed"), Exception)

    def test_transcribe_error(self) -> None:
        """TranscribeError is an Exception subclass."""
        assert isinstance(TranscribeError("transcribe failed"), Exception)

    def test_tab_engine_error(self) -> None:
        """TabEngineError is an Exception subclass."""
        assert isinstance(TabEngineError("tab failed"), Exception)

    def test_exceptions_can_be_raised_and_caught(self) -> None:
        """Each custom exception can be raised and caught by its own type."""
        for exc_cls in (DownloadError, SeparationError, TranscribeError, TabEngineError):
            with pytest.raises(exc_cls):
                raise exc_cls("test")

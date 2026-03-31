"""Tests for data models."""

import pytest

from src.models import BassConfig, FretPosition, NoteEvent, Strategy


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

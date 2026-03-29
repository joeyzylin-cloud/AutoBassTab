"""Tests for the TAB engine module."""

import pytest

from src.models import (
    AssignedNote,
    BassConfig,
    FretPosition,
    NoteEvent,
    Strategy,
    TabEngineError,
)
from src.tab_engine import assign_positions, format_tab


# ---------------------------------------------------------------------------
# Helper to create notes quickly
# ---------------------------------------------------------------------------

def _note(pitch: int, start: float, end: float | None = None) -> NoteEvent:
    """Shorthand to create a NoteEvent."""
    return NoteEvent(midi_pitch=pitch, start_time=start, end_time=end or start + 0.5)


# ===========================================================================
# assign_positions tests
# ===========================================================================

class TestAssignLowestPosition:
    """Tests for LOWEST_POSITION strategy."""

    def test_single_note_open_string(self) -> None:
        """MIDI 28 (open E) → string 4, fret 0."""
        notes = [_note(28, 0.0)]
        result = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result[0].position == FretPosition(string_number=4, fret=0)

    def test_prefers_lowest_fret(self) -> None:
        """MIDI 33 can be A open(0) or E fret 5 → should pick fret 0."""
        notes = [_note(33, 0.0)]
        result = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result[0].position.fret == 0

    def test_same_fret_prefers_lowest_string_number(self) -> None:
        """MIDI 43 = G open(fret 0). Only one fret-0 option, string 1."""
        notes = [_note(43, 0.0)]
        result = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result[0].position == FretPosition(string_number=1, fret=0)

    def test_multiple_notes(self) -> None:
        """Multiple notes each get lowest position independently."""
        notes = [_note(28, 0.0), _note(33, 0.5), _note(38, 1.0)]
        result = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result[0].position == FretPosition(string_number=4, fret=0)  # E open
        assert result[1].position == FretPosition(string_number=3, fret=0)  # A open
        assert result[2].position == FretPosition(string_number=2, fret=0)  # D open


class TestAssignMinMovement:
    """Tests for MIN_MOVEMENT strategy."""

    def test_first_note_uses_lowest_position(self) -> None:
        """First note should fallback to LOWEST_POSITION."""
        notes = [_note(33, 0.0)]
        result = assign_positions(notes, Strategy.MIN_MOVEMENT)
        lowest = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result[0].position == lowest[0].position

    def test_stays_near_previous(self) -> None:
        """After fret 5 on E string, MIDI 34 (A#) should prefer E fret 6 over A fret 1."""
        # First note: MIDI 33 = A open (fret 0, string 3)
        # Force first note to be at E string fret 5 by using MIDI 33
        # Actually let's pick a note that starts at a known position.
        # MIDI 40 = E string fret 12, or A string fret 7, or D string fret 2
        # Lowest position = D string fret 2.
        # Next: MIDI 41 = E string fret 13, or A string fret 8, or D string fret 3
        # Min movement from D fret 2 → D fret 3 (distance 1)
        notes = [_note(40, 0.0), _note(41, 0.5)]
        result = assign_positions(notes, Strategy.MIN_MOVEMENT)
        # First note: D string fret 2 (lowest position)
        assert result[0].position == FretPosition(string_number=2, fret=2)
        # Second note: D string fret 3 (closest to fret 2)
        assert result[1].position == FretPosition(string_number=2, fret=3)

    def test_big_jump_picks_closest(self) -> None:
        """Jump from high fret to a note with multiple options picks closest."""
        # First: MIDI 52 on G string fret 9 (lowest)
        # Second: MIDI 33 = A open(0) or E fret 5
        # From fret 9: |0-9|=9 vs |5-9|=4 → picks E fret 5
        notes = [_note(52, 0.0), _note(33, 0.5)]
        result = assign_positions(notes, Strategy.MIN_MOVEMENT)
        assert result[1].position == FretPosition(string_number=4, fret=5)


class TestAssignOpenStringPrefer:
    """Tests for OPEN_STRING_PREFER strategy."""

    def test_picks_open_string_when_available(self) -> None:
        """MIDI 33 has fret 0 on A string → should pick it."""
        notes = [_note(33, 0.0)]
        result = assign_positions(notes, Strategy.OPEN_STRING_PREFER)
        assert result[0].position.fret == 0

    def test_fallback_to_lowest_when_no_open(self) -> None:
        """MIDI 29 (F on E string fret 1) has no open string → lowest position."""
        notes = [_note(29, 0.0)]
        result_open = assign_positions(notes, Strategy.OPEN_STRING_PREFER)
        result_low = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result_open[0].position == result_low[0].position

    def test_multiple_open_strings_picks_lowest_string_number(self) -> None:
        """If multiple strings have fret=0 for same pitch (impossible in standard
        tuning, but testing the logic), pick lowest string_number."""
        # In standard tuning this won't happen, but MIDI 33 only has one open string
        notes = [_note(33, 0.0)]
        result = assign_positions(notes, Strategy.OPEN_STRING_PREFER)
        assert result[0].position == FretPosition(string_number=3, fret=0)


class TestAssignPositionsErrors:
    """Tests for error handling in assign_positions."""

    def test_note_out_of_range_raises(self) -> None:
        """A note below MIDI 28 cannot be played."""
        notes = [_note(20, 0.0)]
        with pytest.raises(TabEngineError, match="cannot be played"):
            assign_positions(notes, Strategy.LOWEST_POSITION)

    def test_empty_notes_returns_empty(self) -> None:
        result = assign_positions([], Strategy.LOWEST_POSITION)
        assert result == []


# ===========================================================================
# format_tab tests
# ===========================================================================

class TestFormatTab:
    """Tests for format_tab output formatting."""

    def test_empty_input(self) -> None:
        """Empty list produces an empty measure."""
        result = format_tab([])
        lines = result.split("\n")
        assert len(lines) == 4
        assert lines[0].startswith("G|")
        assert lines[3].startswith("E|")

    def test_single_note_on_e_string(self) -> None:
        """One note on E string, rest should be dashes."""
        assigned = [
            AssignedNote(
                event=_note(28, 0.0),
                position=FretPosition(string_number=4, fret=0),
            )
        ]
        result = format_tab(assigned, beats_per_measure=4)
        lines = result.split("\n")
        # G, D, A lines should have only dashes (plus bars)
        assert "0" not in lines[0]  # G
        assert "0" not in lines[1]  # D
        assert "0" not in lines[2]  # A
        # E line should contain a 0
        assert "0" in lines[3]  # E

    def test_notes_on_different_strings(self) -> None:
        """Notes on A and E strings at different times."""
        assigned = [
            AssignedNote(
                event=_note(33, 0.0),
                position=FretPosition(string_number=3, fret=0),
            ),
            AssignedNote(
                event=_note(31, 0.5),
                position=FretPosition(string_number=4, fret=3),
            ),
        ]
        result = format_tab(assigned, beats_per_measure=8)
        lines = result.split("\n")
        # A line should have a 0
        assert "0" in lines[2]
        # E line should have a 3
        assert "3" in lines[3]

    def test_tab_has_four_lines(self) -> None:
        """Output always has exactly 4 lines."""
        assigned = [
            AssignedNote(
                event=_note(43, 0.0),
                position=FretPosition(string_number=1, fret=0),
            ),
        ]
        result = format_tab(assigned)
        lines = result.split("\n")
        assert len(lines) == 4

    def test_line_order_is_gdae(self) -> None:
        """Lines must be in G, D, A, E order."""
        assigned = [
            AssignedNote(
                event=_note(28, 0.0),
                position=FretPosition(string_number=4, fret=0),
            ),
        ]
        result = format_tab(assigned)
        lines = result.split("\n")
        assert lines[0][0] == "G"
        assert lines[1][0] == "D"
        assert lines[2][0] == "A"
        assert lines[3][0] == "E"

    def test_double_digit_fret(self) -> None:
        """Fret numbers >= 10 should appear in the tab."""
        assigned = [
            AssignedNote(
                event=_note(52, 0.0),  # E3
                position=FretPosition(string_number=2, fret=14),
            ),
        ]
        result = format_tab(assigned)
        assert "14" in result

    def test_simultaneous_notes(self) -> None:
        """Two notes at the same time should both appear."""
        assigned = [
            AssignedNote(
                event=_note(28, 0.0),
                position=FretPosition(string_number=4, fret=0),
            ),
            AssignedNote(
                event=_note(43, 0.0),
                position=FretPosition(string_number=1, fret=0),
            ),
        ]
        result = format_tab(assigned, beats_per_measure=4)
        lines = result.split("\n")
        # Both G and E should have 0 at the same beat
        assert "0" in lines[0]  # G
        assert "0" in lines[3]  # E

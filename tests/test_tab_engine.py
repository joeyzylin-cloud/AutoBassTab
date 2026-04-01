"""Tests for the TAB engine module."""

from pathlib import Path

import pretty_midi
import pytest

from src.models import (
    AssignedNote,
    BassConfig,
    FretPosition,
    NoteEvent,
    Strategy,
    TabEngineError,
)
from src.tab_engine import (
    _decompose_duration,
    _snap_rhythm,
    assign_positions,
    detect_bpm,
    format_tab,
    load_midi_notes,
)


# ---------------------------------------------------------------------------
# Helper to create notes quickly
# ---------------------------------------------------------------------------

def _note(pitch: int, start: float, end: float | None = None) -> NoteEvent:
    """Shorthand to create a NoteEvent."""
    return NoteEvent(midi_pitch=pitch, start_time=start, end_time=end or start + 0.5)


def _assigned(string: int, fret: int, start: float, end: float | None = None) -> AssignedNote:
    """Shorthand to create an AssignedNote."""
    return AssignedNote(
        event=_note(28, start, end),
        position=FretPosition(string_number=string, fret=fret),
    )


# ===========================================================================
# _snap_rhythm tests
# ===========================================================================

class TestSnapRhythm:
    """Tests for rhythm quantization."""

    def test_exact_quarter(self) -> None:
        sym, val = _snap_rhythm(1.0)
        assert sym == "Q"
        assert val == 1.0

    def test_exact_eighth(self) -> None:
        sym, val = _snap_rhythm(0.5)
        assert sym == "E"

    def test_exact_half(self) -> None:
        sym, val = _snap_rhythm(2.0)
        assert sym == "H"

    def test_exact_whole(self) -> None:
        sym, val = _snap_rhythm(4.0)
        assert sym == "W"

    def test_exact_sixteenth(self) -> None:
        sym, val = _snap_rhythm(0.25)
        assert sym == "S"

    def test_dotted_quarter(self) -> None:
        sym, val = _snap_rhythm(1.5)
        assert sym == "Q."

    def test_within_tolerance(self) -> None:
        """0.95 beats is within 10% of Q (1.0)."""
        sym, _ = _snap_rhythm(0.95)
        assert sym == "Q"

    def test_snaps_to_closest(self) -> None:
        """A value far from any standard should snap to closest."""
        sym, _ = _snap_rhythm(0.3)
        assert sym == "S"  # 0.25 is closest


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
        # MIDI 40: D fret 2 (lowest). Next MIDI 41: D fret 3 (closest to 2)
        notes = [_note(40, 0.0), _note(41, 0.5)]
        result = assign_positions(notes, Strategy.MIN_MOVEMENT)
        assert result[0].position == FretPosition(string_number=2, fret=2)
        assert result[1].position == FretPosition(string_number=2, fret=3)

    def test_big_jump_picks_closest(self) -> None:
        # MIDI 52 → G fret 9. Then MIDI 33: B fret 10 is closest to fret 9
        notes = [_note(52, 0.0), _note(33, 0.5)]
        result = assign_positions(notes, Strategy.MIN_MOVEMENT)
        assert result[1].position == FretPosition(string_number=5, fret=10)


class TestAssignOpenStringPrefer:
    """Tests for OPEN_STRING_PREFER strategy."""

    def test_picks_open_string_when_available(self) -> None:
        notes = [_note(33, 0.0)]
        result = assign_positions(notes, Strategy.OPEN_STRING_PREFER)
        assert result[0].position.fret == 0

    def test_fallback_to_lowest_when_no_open(self) -> None:
        notes = [_note(29, 0.0)]
        result_open = assign_positions(notes, Strategy.OPEN_STRING_PREFER)
        result_low = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result_open[0].position == result_low[0].position

    def test_multiple_open_strings_picks_lowest_string_number(self) -> None:
        notes = [_note(33, 0.0)]
        result = assign_positions(notes, Strategy.OPEN_STRING_PREFER)
        assert result[0].position == FretPosition(string_number=3, fret=0)


class TestAssignPositionsErrors:
    """Tests for error handling in assign_positions."""

    def test_note_out_of_range_skipped(self) -> None:
        notes = [_note(20, 0.0)]
        result = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result == []

    def test_b_string_note_assigned(self) -> None:
        notes = [_note(23, 0.0)]
        result = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result[0].position == FretPosition(string_number=5, fret=0)

    def test_midi_25_now_playable(self) -> None:
        notes = [_note(25, 0.0)]
        result = assign_positions(notes, Strategy.LOWEST_POSITION)
        assert result[0].position == FretPosition(string_number=5, fret=2)

    def test_empty_notes_returns_empty(self) -> None:
        result = assign_positions([], Strategy.LOWEST_POSITION)
        assert result == []


# ===========================================================================
# format_tab tests
# ===========================================================================

class TestFormatTab:
    """Tests for rhythm + TAB dual-layer formatting."""

    def test_empty_input(self) -> None:
        """Empty list produces header + empty measure structure."""
        result = format_tab([])
        assert "♩=" in result
        assert "G|" in result
        assert "E|" in result

    def test_single_note_on_e_string(self) -> None:
        """One note on E string: E line has fret, others are dashes."""
        assigned = [_assigned(4, 0, 0.0, 0.5)]
        result = format_tab(assigned, bpm=120.0)
        lines = result.split("\n")
        # Find the string lines (start with G|, D|, A|, E|)
        tab_lines = [l for l in lines if len(l) > 1 and l[1] == "|"]
        e_line = [l for l in tab_lines if l[0] == "E"][0]
        assert "0" in e_line

    def test_bpm_header(self) -> None:
        """Output starts with BPM marker."""
        assigned = [_assigned(3, 5, 0.0, 0.5)]
        result = format_tab(assigned, bpm=140.0)
        assert result.startswith("♩=140")

    def test_rhythm_symbols_present(self) -> None:
        """Rhythm line contains note duration symbols."""
        # Two eighth notes (0.5s each at 120 BPM = 1 beat each → Q)
        # Actually at 120 BPM, 0.5s = 1 beat = Q
        assigned = [
            _assigned(3, 5, 0.0, 0.5),
            _assigned(3, 7, 0.5, 1.0),
        ]
        result = format_tab(assigned, bpm=120.0)
        # Should contain Q (quarter note) symbols
        assert "Q" in result

    def test_four_lines_when_no_b_string(self) -> None:
        """Only G/D/A/E tab lines when no notes use B string."""
        assigned = [_assigned(1, 0, 0.0, 0.5)]
        result = format_tab(assigned, bpm=120.0)
        tab_lines = [l for l in result.split("\n") if len(l) > 1 and l[1] == "|"]
        string_prefixes = [l[0] for l in tab_lines]
        assert "B" not in string_prefixes
        assert "G" in string_prefixes
        assert "E" in string_prefixes

    def test_five_lines_when_b_string_used(self) -> None:
        """G/D/A/E/B tab lines when B string is used."""
        assigned = [
            _assigned(5, 0, 0.0, 0.5),
            _assigned(4, 0, 0.5, 1.0),
        ]
        result = format_tab(assigned, bpm=120.0)
        tab_lines = [l for l in result.split("\n") if len(l) > 1 and l[1] == "|"]
        string_prefixes = [l[0] for l in tab_lines]
        assert "B" in string_prefixes

    def test_line_order_is_gdaeb(self) -> None:
        """Tab lines are in G, D, A, E, B order."""
        assigned = [_assigned(5, 2, 0.0, 0.5)]
        result = format_tab(assigned, bpm=120.0)
        tab_lines = [l for l in result.split("\n") if len(l) > 1 and l[1] == "|" and l[0] in "GDAEB"]
        order = [l[0] for l in tab_lines]
        assert order == ["G", "D", "A", "E", "B"]

    def test_double_digit_fret(self) -> None:
        """Fret numbers >= 10 appear correctly in output."""
        assigned = [_assigned(2, 14, 0.0, 0.5)]
        result = format_tab(assigned, bpm=120.0)
        assert "14" in result

    def test_simultaneous_notes(self) -> None:
        """Two notes at same time both appear in output."""
        assigned = [
            _assigned(4, 0, 0.0, 0.5),
            _assigned(1, 0, 0.0, 0.5),
        ]
        result = format_tab(assigned, bpm=120.0)
        tab_lines = [l for l in result.split("\n") if len(l) > 1 and l[1] == "|"]
        g_line = [l for l in tab_lines if l[0] == "G"][0]
        e_line = [l for l in tab_lines if l[0] == "E"][0]
        assert "0" in g_line
        assert "0" in e_line

    def test_measure_numbers_present(self) -> None:
        """Output contains measure numbers."""
        assigned = [_assigned(3, 5, 0.0, 0.5)]
        result = format_tab(assigned, bpm=120.0)
        assert "1" in result

    def test_rest_symbols_for_gaps(self) -> None:
        """Gaps between notes produce rest symbols (containing 'r')."""
        # Note at beat 0, then gap, then note at beat 2
        # At 120 BPM: beat 0 = 0.0s, beat 2 = 1.0s
        assigned = [
            _assigned(3, 5, 0.0, 0.25),   # E at 120bpm = 0.5 beats
            _assigned(3, 7, 1.0, 1.25),   # starts at beat 2
        ]
        result = format_tab(assigned, bpm=120.0)
        assert "r" in result  # rest symbol present

    def test_rhythm_and_tab_alignment(self) -> None:

        """Rhythm line and TAB lines have same width between | delimiters."""
        assigned = [
            _assigned(3, 0, 0.0, 0.5),
            _assigned(3, 5, 0.5, 1.0),
            _assigned(3, 7, 1.0, 1.5),
        ]
        result = format_tab(assigned, bpm=120.0)
        lines = result.split("\n")

        # Find lines that contain | delimiters (non-empty, non-header)
        bar_lines = [l for l in lines if "|" in l and l.strip()]
        if len(bar_lines) >= 2:
            # All bar-containing lines should have same length
            lengths = [len(l) for l in bar_lines]
            assert len(set(lengths)) == 1, f"Misaligned lines: {lengths}"


# ===========================================================================
# _decompose_duration tests
# ===========================================================================

class TestDecomposeDuration:
    """Tests for _decompose_duration()."""

    def test_quarter_returns_single_q(self) -> None:
        """1.0 beat decomposes to a single quarter note."""
        parts = _decompose_duration(1.0)
        assert parts == [("Q", 1.0)]

    def test_dotted_half_returns_single_h_dot(self) -> None:
        """3.0 beats decomposes to a single dotted half note."""
        parts = _decompose_duration(3.0)
        assert parts == [("H.", 3.0)]

    def test_two_and_half_beats_sums_correctly(self) -> None:
        """2.5 beats decomposes to parts that sum back to 2.5."""
        parts = _decompose_duration(2.5)
        total = sum(v for _, v in parts)
        assert abs(total - 2.5) < 0.01

    def test_very_small_returns_sixteenth(self) -> None:
        """Input below the loop threshold returns at least a sixteenth note."""
        parts = _decompose_duration(0.05)
        assert parts == [("S", 0.25)]

    def test_always_returns_nonempty(self) -> None:
        """Result is never empty for any positive input."""
        for beats in [0.25, 0.5, 1.0, 2.0, 3.5, 4.0]:
            assert len(_decompose_duration(beats)) > 0


# ===========================================================================
# detect_bpm tests
# ===========================================================================

def _write_midi(tmp_path: Path, bpm: float | None = None) -> Path:
    """Write a minimal MIDI file and return its path."""
    mid = pretty_midi.PrettyMIDI(initial_tempo=bpm if bpm else 120.0)
    inst = pretty_midi.Instrument(program=33)  # electric bass
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=40, start=0.0, end=0.5))
    mid.instruments.append(inst)
    path = tmp_path / "test.mid"
    mid.write(str(path))
    return path


class TestDetectBpm:
    """Tests for detect_bpm()."""

    def test_reads_explicit_tempo(self, tmp_path: Path) -> None:
        """Reads the tempo embedded in a MIDI file."""
        path = _write_midi(tmp_path, bpm=140.0)
        result = detect_bpm(path)
        assert abs(result - 140.0) < 1.0

    def test_returns_120_for_missing_file(self, tmp_path: Path) -> None:
        """Returns 120.0 gracefully when file does not exist."""
        result = detect_bpm(tmp_path / "nonexistent.mid")
        assert result == 120.0


# ===========================================================================
# load_midi_notes tests
# ===========================================================================

class TestLoadMidiNotes:
    """Tests for load_midi_notes()."""

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Raises TabEngineError when MIDI file is missing."""
        with pytest.raises(TabEngineError, match="not found"):
            load_midi_notes(tmp_path / "missing.mid")

    def test_empty_midi_returns_empty_list(self, tmp_path: Path) -> None:
        """MIDI file with no notes returns an empty list."""
        mid = pretty_midi.PrettyMIDI()
        path = tmp_path / "empty.mid"
        mid.write(str(path))
        assert load_midi_notes(path) == []

    def test_drum_track_excluded(self, tmp_path: Path) -> None:
        """Notes on a drum instrument are excluded from results."""
        mid = pretty_midi.PrettyMIDI()
        drum = pretty_midi.Instrument(program=0, is_drum=True)
        drum.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0.0, end=0.1))
        mid.instruments.append(drum)
        path = tmp_path / "drums.mid"
        mid.write(str(path))
        assert load_midi_notes(path) == []

    def test_non_drum_notes_loaded(self, tmp_path: Path) -> None:
        """Notes on a non-drum instrument are returned."""
        path = _write_midi(tmp_path, bpm=120.0)
        notes = load_midi_notes(path)
        assert len(notes) == 1
        assert notes[0].midi_pitch == 40

    def test_notes_sorted_by_start_time(self, tmp_path: Path) -> None:
        """Notes are returned sorted by start_time regardless of insertion order."""
        mid = pretty_midi.PrettyMIDI()
        inst = pretty_midi.Instrument(program=33)
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=33, start=1.0, end=1.5))
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=40, start=0.0, end=0.5))
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=38, start=0.5, end=1.0))
        mid.instruments.append(inst)
        path = tmp_path / "unsorted.mid"
        mid.write(str(path))
        notes = load_midi_notes(path)
        starts = [n.start_time for n in notes]
        assert starts == sorted(starts)

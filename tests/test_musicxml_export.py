"""Tests for MusicXML export module."""

from pathlib import Path

import pytest

from src.models import AssignedNote, FretPosition, NoteEvent
from src.musicxml_export import (
    _beats_to_div,
    _midi_to_pitch_parts,
    export_musicxml,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _note(pitch: int, start: float, end: float) -> NoteEvent:
    """Shorthand to create a NoteEvent."""
    return NoteEvent(midi_pitch=pitch, start_time=start, end_time=end, velocity=80)


def _assigned(string: int, fret: int, start: float, end: float) -> AssignedNote:
    """Shorthand to create an AssignedNote."""
    midi = {1: 43, 2: 38, 3: 33, 4: 28, 5: 23}[string] + fret
    return AssignedNote(
        event=_note(midi, start, end),
        position=FretPosition(string_number=string, fret=fret),
    )


# ===========================================================================
# _midi_to_pitch_parts
# ===========================================================================

class TestMidiToPitchParts:
    """Tests for _midi_to_pitch_parts()."""

    def test_e1_midi_28(self) -> None:
        """MIDI 28 = E1."""
        step, alter, octave = _midi_to_pitch_parts(28)
        assert step == "E"
        assert alter == 0
        assert octave == 1

    def test_a1_midi_33(self) -> None:
        """MIDI 33 = A1."""
        step, alter, octave = _midi_to_pitch_parts(33)
        assert step == "A"
        assert alter == 0
        assert octave == 1

    def test_g2_midi_43(self) -> None:
        """MIDI 43 = G2."""
        step, alter, octave = _midi_to_pitch_parts(43)
        assert step == "G"
        assert alter == 0
        assert octave == 2

    def test_csharp_midi_25(self) -> None:
        """MIDI 25 = C#1: alter should be 1."""
        step, alter, octave = _midi_to_pitch_parts(25)
        assert alter == 1
        assert octave == 1


# ===========================================================================
# _beats_to_div
# ===========================================================================

class TestBeatsToDivisions:
    """Tests for _beats_to_div()."""

    def test_quarter_note_is_16_divisions(self) -> None:
        """1.0 beat = 16 divisions (one quarter at _DIVISIONS=16)."""
        assert _beats_to_div(1.0) == 16

    def test_eighth_note_is_8_divisions(self) -> None:
        """0.5 beats = 8 divisions."""
        assert _beats_to_div(0.5) == 8

    def test_half_note_is_32_divisions(self) -> None:
        """2.0 beats = 32 divisions."""
        assert _beats_to_div(2.0) == 32

    def test_minimum_is_1(self) -> None:
        """Very small input still produces at least 1 division."""
        assert _beats_to_div(0.001) >= 1


# ===========================================================================
# export_musicxml
# ===========================================================================

class TestExportMusicxml:
    """Tests for export_musicxml()."""

    def test_empty_assigned_returns_valid_xml(self) -> None:
        """Empty input produces a well-formed XML string with DOCTYPE."""
        result = export_musicxml([])
        assert '<?xml version="1.0"' in result
        assert "score-partwise" in result
        assert "DOCTYPE" in result

    def test_single_note_has_fret_and_string_elements(self) -> None:
        """A single note produces correct <fret> and <string> elements."""
        assigned = [_assigned(4, 0, 0.0, 0.5)]  # open E string
        result = export_musicxml(assigned)
        assert "<fret>0</fret>" in result
        assert "<string>4</string>" in result

    def test_chord_second_note_has_chord_element(self) -> None:
        """Two simultaneous notes: the second one must contain <chord/>."""
        assigned = [
            _assigned(4, 0, 0.0, 0.5),
            _assigned(1, 0, 0.0, 0.5),
        ]
        result = export_musicxml(assigned)
        assert "<chord/>" in result or "<chord />" in result

    def test_bpm_metronome_marker(self) -> None:
        """Output contains the correct BPM in <per-minute>."""
        result = export_musicxml([], bpm=140.0)
        assert "<per-minute>140</per-minute>" in result

    def test_4_string_staff_when_no_b_string(self) -> None:
        """Notes on strings 1-4 only → staff-lines=4."""
        assigned = [_assigned(4, 0, 0.0, 0.5)]
        result = export_musicxml(assigned)
        assert "<staff-lines>4</staff-lines>" in result

    def test_5_string_staff_when_b_string_used(self) -> None:
        """A note on string 5 → staff-lines=5."""
        assigned = [_assigned(5, 0, 0.0, 0.5)]
        result = export_musicxml(assigned)
        assert "<staff-lines>5</staff-lines>" in result

    def test_writes_file_when_output_path_given(self, tmp_path: Path) -> None:
        """Writes XML to file when output_path is provided."""
        out = tmp_path / "out.xml"
        export_musicxml([], output_path=out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_file_contents_match_return_value(self, tmp_path: Path) -> None:
        """File contents are identical to the return value."""
        out = tmp_path / "out.xml"
        result = export_musicxml([], output_path=out)
        assert out.read_text(encoding="utf-8") == result

    def test_rest_appears_for_gap_between_notes(self) -> None:
        """A gap between notes produces a <rest/> element."""
        assigned = [
            _assigned(4, 0, 0.0, 0.25),
            _assigned(4, 5, 1.0, 1.25),  # gap of 0.75s at 120 BPM
        ]
        result = export_musicxml(assigned, bpm=120.0)
        assert "<rest/>" in result or "<rest />" in result

"""MusicXML export for bass TAB notation."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

from src.models import AssignedNote
from src.tab_engine import _decompose_duration, _snap_rhythm

_DIVISIONS = 16  # XML duration units per quarter note

# Chromatic pitch table: pc → (step, alter)
_PITCH_TABLE = [
    ("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0),
    ("F", 0), ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0),
]

# Rhythm symbol → MusicXML note type
_TYPE_MAP = {
    "W": "whole",   "W.": "whole",
    "H": "half",    "H.": "half",
    "Q": "quarter", "Q.": "quarter",
    "E": "eighth",  "E.": "eighth",
    "S": "16th",    "S.": "16th",
}

# Open string MIDI pitches (string_number → midi)
_OPEN_MIDI = {1: 43, 2: 38, 3: 33, 4: 28, 5: 23}

# Open string tuning for staff-details (string_number → (step, alter, octave))
_STRING_TUNING = {
    1: ("G", 0, 2),  # G2 = MIDI 43
    2: ("D", 0, 2),  # D2 = MIDI 38
    3: ("A", 0, 1),  # A1 = MIDI 33
    4: ("E", 0, 1),  # E1 = MIDI 28
    5: ("B", 0, 0),  # B0 = MIDI 23
}


def _midi_to_pitch_parts(midi: int) -> tuple[str, int, int]:
    """Return (step, alter, octave) for a MIDI pitch number."""
    step, alter = _PITCH_TABLE[midi % 12]
    octave = (midi // 12) - 1
    return step, alter, octave


def _beats_to_div(beats: float) -> int:
    return max(1, round(beats * _DIVISIONS))


def _add_attributes(
    parent: ET.Element,
    n_strings: int,
    first_measure: bool,
    beats_per_measure: int,
) -> None:
    """Append <attributes> to a measure element."""
    attr = ET.SubElement(parent, "attributes")
    ET.SubElement(attr, "divisions").text = str(_DIVISIONS)
    if first_measure:
        key = ET.SubElement(attr, "key")
        ET.SubElement(key, "fifths").text = "0"
        time = ET.SubElement(attr, "time")
        ET.SubElement(time, "beats").text = str(beats_per_measure)
        ET.SubElement(time, "beat-type").text = "4"
        clef = ET.SubElement(attr, "clef")
        ET.SubElement(clef, "sign").text = "TAB"
        sd = ET.SubElement(attr, "staff-details")
        ET.SubElement(sd, "staff-lines").text = str(n_strings)
        for s in range(1, n_strings + 1):
            step, alter, octave = _STRING_TUNING[s]
            tuning = ET.SubElement(sd, "staff-tuning", line=str(s))
            ET.SubElement(tuning, "tuning-step").text = step
            if alter:
                ET.SubElement(tuning, "tuning-alter").text = str(alter)
            ET.SubElement(tuning, "tuning-octave").text = str(octave)


def _add_note_elements(
    measure_el: ET.Element,
    frets: dict[int, int],
    beats: float,
    sym: str,
) -> None:
    """Add <note> elements for a chord (one or more simultaneous notes)."""
    base_sym = sym.rstrip("r")
    note_type = _TYPE_MAP.get(base_sym, "quarter")
    div = _beats_to_div(beats)
    dotted = base_sym.endswith(".")

    for i, string_num in enumerate(sorted(frets.keys())):
        fret = frets[string_num]
        midi = _OPEN_MIDI[string_num] + fret
        step, alter, octave = _midi_to_pitch_parts(midi)

        note_el = ET.SubElement(measure_el, "note")
        if i > 0:
            ET.SubElement(note_el, "chord")

        pitch_el = ET.SubElement(note_el, "pitch")
        ET.SubElement(pitch_el, "step").text = step
        if alter:
            ET.SubElement(pitch_el, "alter").text = str(alter)
        ET.SubElement(pitch_el, "octave").text = str(octave)

        ET.SubElement(note_el, "duration").text = str(div)
        ET.SubElement(note_el, "type").text = note_type
        if dotted:
            ET.SubElement(note_el, "dot")

        notations = ET.SubElement(note_el, "notations")
        technical = ET.SubElement(notations, "technical")
        ET.SubElement(technical, "string").text = str(string_num)
        ET.SubElement(technical, "fret").text = str(fret)


def _add_rest_element(
    measure_el: ET.Element,
    beats: float,
    sym: str,
) -> None:
    """Add a <note><rest/></note> element."""
    base_sym = sym.rstrip("r")
    note_type = _TYPE_MAP.get(base_sym, "quarter")
    div = _beats_to_div(beats)
    dotted = base_sym.endswith(".")

    note_el = ET.SubElement(measure_el, "note")
    ET.SubElement(note_el, "rest")
    ET.SubElement(note_el, "duration").text = str(div)
    ET.SubElement(note_el, "type").text = note_type
    if dotted:
        ET.SubElement(note_el, "dot")


def export_musicxml(
    assigned: list[AssignedNote],
    bpm: float = 120.0,
    beats_per_measure: int = 4,
    output_path: Path | None = None,
) -> str:
    """Export assigned notes as a MusicXML string.

    Produces a TAB-clef score compatible with MuseScore, Guitar Pro, etc.

    Args:
        assigned: List of AssignedNote sorted by start_time.
        bpm: Tempo in BPM.
        beats_per_measure: Time signature numerator (4 = 4/4 time).
        output_path: If given, write UTF-8 XML to this path.

    Returns:
        MusicXML content as a UTF-8 string.
    """
    n_strings = 5 if assigned and max(a.position.string_number for a in assigned) >= 5 else 4

    # --- Build beat-space timeline (mirrors format_tab logic) ---
    beat_events: list[tuple[float, float, int, int]] = []
    for an in sorted(assigned, key=lambda a: a.event.start_time):
        s_beat = an.event.start_time * bpm / 60.0
        dur = (an.event.end_time - an.event.start_time) * bpm / 60.0
        beat_events.append((s_beat, dur, an.position.string_number, an.position.fret))

    # Group simultaneous notes
    groups: list[tuple[float, float, str, dict[int, int]]] = []
    i = 0
    while i < len(beat_events):
        start, dur, string, fret = beat_events[i]
        frets: dict[int, int] = {string: fret}
        max_dur = dur
        j = i + 1
        while j < len(beat_events) and abs(beat_events[j][0] - start) < 0.05:
            _, d, s, f = beat_events[j]
            frets[s] = f
            max_dur = max(max_dur, d)
            j += 1
        sym, snapped = _snap_rhythm(max_dur)
        groups.append((start, snapped, sym, frets))
        i = j

    # Insert rests for gaps
    timeline: list[tuple[str, float, dict[int, int]]] = []
    current_beat = 0.0
    for start, dur, sym, frets in groups:
        gap = start - current_beat
        if gap > 0.12:
            for r_sym, r_beats in _decompose_duration(gap):
                timeline.append((r_sym + "r", r_beats, {}))
            current_beat = start
        timeline.append((sym, dur, frets))
        current_beat = start + dur

    # --- Split timeline into measures ---
    measures: list[list[tuple[str, float, dict[int, int]]]] = []
    m_events: list[tuple[str, float, dict[int, int]]] = []
    m_beats_used = 0.0

    for sym, beats, frets in timeline:
        remaining = beats
        while remaining > 0.01:
            space = beats_per_measure - m_beats_used
            take = min(remaining, space)
            if abs(take - beats) < 0.01:
                chunk_sym = sym
            else:
                cs, _ = _snap_rhythm(take)
                chunk_sym = cs + ("r" if sym.endswith("r") else "")
            m_events.append((chunk_sym, take, frets if not sym.endswith("r") else {}))
            m_beats_used += take
            remaining -= take
            if m_beats_used >= beats_per_measure - 0.01:
                measures.append(m_events)
                m_events = []
                m_beats_used = 0.0

    if m_events:
        space = beats_per_measure - m_beats_used
        if space > 0.01:
            for rs, rb in _decompose_duration(space):
                m_events.append((rs + "r", rb, {}))
        measures.append(m_events)

    if not measures:
        measures = [[("Wr", float(beats_per_measure), {})]]

    # --- Build XML tree ---
    root = ET.Element("score-partwise", version="3.1")

    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = "Bass Guitar"

    part = ET.SubElement(root, "part", id="P1")

    for m_idx, m_evs in enumerate(measures):
        m_el = ET.SubElement(part, "measure", number=str(m_idx + 1))

        if m_idx == 0:
            direction = ET.SubElement(m_el, "direction", placement="above")
            dir_type = ET.SubElement(direction, "direction-type")
            metro = ET.SubElement(dir_type, "metronome", parentheses="no")
            ET.SubElement(metro, "beat-unit").text = "quarter"
            ET.SubElement(metro, "per-minute").text = str(int(bpm))
            ET.SubElement(direction, "sound", tempo=str(int(bpm)))

        _add_attributes(m_el, n_strings, first_measure=(m_idx == 0), beats_per_measure=beats_per_measure)

        for sym, beats, frets in m_evs:
            if sym.endswith("r"):
                _add_rest_element(m_el, beats, sym)
            else:
                _add_note_elements(m_el, frets, beats, sym)

    # --- Pretty-print with DOCTYPE ---
    raw = ET.tostring(root, encoding="unicode")
    dom = minidom.parseString(raw)
    pretty_lines = dom.toprettyxml(indent="  ").split("\n")
    # Replace minidom's generic declaration with the full MusicXML header
    header = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC\n'
        '  "-//Recordare//DTD MusicXML 3.1 Partwise//EN"\n'
        '  "http://www.musicxml.org/dtds/partwise.dtd">'
    )
    result = header + "\n" + "\n".join(pretty_lines[1:])

    if output_path is not None:
        output_path.write_text(result, encoding="utf-8")

    return result

"""Module 4: MIDI to bass TAB conversion engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from src.models import (
    AssignedNote,
    BassConfig,
    FretPosition,
    NoteEvent,
    Strategy,
    TabConfig,
    TabEngineError,
)

# String display order: G, D, A, E, B (string numbers 1-5)
_STRING_NAMES = {1: "G", 2: "D", 3: "A", 4: "E", 5: "B"}


def load_midi_notes(midi_path: Path) -> list[NoteEvent]:
    """Load notes from a MIDI file and return as NoteEvent list.

    Args:
        midi_path: Path to the MIDI file.

    Returns:
        List of NoteEvent sorted by start_time.

    Raises:
        TabEngineError: If the MIDI file cannot be read.
    """
    try:
        import pretty_midi
    except ImportError as e:
        raise TabEngineError(
            "pretty_midi is not installed. Install with: pip install pretty-midi"
        ) from e

    if not midi_path.exists():
        raise TabEngineError(f"MIDI file not found: {midi_path}")

    try:
        midi = pretty_midi.PrettyMIDI(str(midi_path))
    except Exception as e:
        raise TabEngineError(f"Failed to read MIDI file: {e}") from e

    notes: list[NoteEvent] = []
    for instrument in midi.instruments:
        if instrument.is_drum:
            continue
        for note in instrument.notes:
            notes.append(
                NoteEvent(
                    midi_pitch=note.pitch,
                    start_time=note.start,
                    end_time=note.end,
                    velocity=note.velocity,
                )
            )

    notes.sort(key=lambda n: n.start_time)
    logger.info("Loaded {} notes from {}", len(notes), midi_path.name)
    return notes


def _pick_lowest_position(
    positions: list[FretPosition],
) -> FretPosition:
    """Pick the position with lowest fret, then lowest string number."""
    return min(positions, key=lambda p: (p.fret, p.string_number))


def _pick_min_movement(
    positions: list[FretPosition],
    prev: FretPosition | None,
) -> FretPosition:
    """Pick the position closest to the previous position.

    Distance = |fret difference|. Falls back to lowest_position for first note.
    """
    if prev is None:
        return _pick_lowest_position(positions)
    return min(positions, key=lambda p: (abs(p.fret - prev.fret), p.fret, p.string_number))


def _pick_open_string_prefer(
    positions: list[FretPosition],
) -> FretPosition:
    """Pick fret=0 if available, otherwise fallback to lowest_position."""
    open_positions = [p for p in positions if p.fret == 0]
    if open_positions:
        return min(open_positions, key=lambda p: p.string_number)
    return _pick_lowest_position(positions)


def assign_positions(
    notes: list[NoteEvent],
    strategy: Strategy,
    bass: BassConfig | None = None,
) -> list[AssignedNote]:
    """Assign fretboard positions to notes using the given strategy.

    Args:
        notes: List of NoteEvent to assign positions to.
        strategy: The fingering strategy to use.
        bass: Bass configuration. Defaults to standard 5-string tuning.

    Returns:
        List of AssignedNote with positions assigned.

    Raises:
        TabEngineError: If a note cannot be played on the bass.
    """
    if bass is None:
        bass = BassConfig()

    assigned: list[AssignedNote] = []
    prev_position: FretPosition | None = None

    for note in notes:
        positions = bass.midi_to_positions(note.midi_pitch)
        if not positions:
            logger.warning(
                "Skipping MIDI pitch {} (out of bass range {}-{})",
                note.midi_pitch,
                bass.tuning[-1].open_midi,
                bass.tuning[0].open_midi + bass.max_fret,
            )
            continue

        if strategy == Strategy.LOWEST_POSITION:
            chosen = _pick_lowest_position(positions)
        elif strategy == Strategy.MIN_MOVEMENT:
            chosen = _pick_min_movement(positions, prev_position)
        elif strategy == Strategy.OPEN_STRING_PREFER:
            chosen = _pick_open_string_prefer(positions)
        else:
            raise TabEngineError(f"Unknown strategy: {strategy}")

        assigned.append(AssignedNote(event=note, position=chosen))
        prev_position = chosen

    logger.info(
        "Assigned {} notes using {} strategy",
        len(assigned),
        strategy.value,
    )
    return assigned


# ---------------------------------------------------------------------------
# Rhythm helpers
# ---------------------------------------------------------------------------

# (symbol, beats) sorted descending — used for snap quantization
_RHYTHM_MAP: list[tuple[str, float]] = [
    ("W.", 6.0),
    ("W", 4.0),
    ("H.", 3.0),
    ("H", 2.0),
    ("Q.", 1.5),
    ("Q", 1.0),
    ("E.", 0.75),
    ("E", 0.5),
    ("S.", 0.375),
    ("S", 0.25),
]

_SNAP_TOLERANCE = 0.10  # ±10%


def _snap_rhythm(beats: float) -> tuple[str, float]:
    """Snap a beat duration to the nearest standard rhythm value.

    Args:
        beats: Duration in beats.

    Returns:
        (symbol, snapped_beats) tuple.
    """
    if beats < 0.01:
        return "S", 0.25
    for sym, val in _RHYTHM_MAP:
        if abs(beats - val) / val <= _SNAP_TOLERANCE:
            return sym, val
    closest = min(_RHYTHM_MAP, key=lambda x: abs(beats - x[1]))
    return closest[0], closest[1]


def _decompose_duration(beats: float) -> list[tuple[str, float]]:
    """Decompose a beat duration into a sequence of standard rhythm values.

    Used when a single rhythm symbol can't represent the duration
    (e.g. 3.5 beats → H. + S or similar).

    Args:
        beats: Duration in beats.

    Returns:
        List of (symbol, beats) tuples.
    """
    parts: list[tuple[str, float]] = []
    remaining = beats
    while remaining > 0.1:
        sym, val = _snap_rhythm(remaining)
        if val > remaining + remaining * _SNAP_TOLERANCE:
            # Find the largest value that fits
            for s, v in _RHYTHM_MAP:
                if v <= remaining + remaining * _SNAP_TOLERANCE:
                    sym, val = s, v
                    break
        parts.append((sym, val))
        remaining -= val
    return parts if parts else [("S", 0.25)]


@dataclass
class _MeasureEvent:
    """A single event (note or rest) within a measure for rendering."""

    rhythm: str  # e.g. "Q", "Er", "H."
    grid_slots: int
    frets: dict[int, int] = field(default_factory=dict)  # string -> fret


def detect_bpm(midi_path: Path) -> float:
    """Detect BPM from a MIDI file.

    Args:
        midi_path: Path to the MIDI file.

    Returns:
        Tempo in BPM. Defaults to 120 if no tempo information found.
    """
    try:
        import pretty_midi
    except ImportError:
        return 120.0
    try:
        midi = pretty_midi.PrettyMIDI(str(midi_path))
        tempos = midi.get_tempo_changes()[1]
        return float(tempos[0]) if len(tempos) > 0 else 120.0
    except Exception:
        return 120.0


# ---------------------------------------------------------------------------
# format_tab — rhythm + TAB dual-layer output
# ---------------------------------------------------------------------------

def format_tab(
    assigned: list[AssignedNote],
    bpm: float = 120.0,
    beats_per_measure: int = 4,
    measures_per_line: int = 4,
) -> str:
    """Format assigned notes as rhythm + TAB dual-layer output.

    Each line of output contains:
    1. Measure number row
    2. Rhythm symbol row (W/H/Q/E/S with dots and rests)
    3. TAB rows for each string (G/D/A/E, optionally B)

    Rhythm symbols align vertically with fret numbers.
    Each grid slot is 3 characters wide.

    Args:
        assigned: List of AssignedNote sorted by start_time.
        bpm: Tempo in beats per minute.
        beats_per_measure: Musical beats per measure (4 = 4/4 time).
        measures_per_line: How many measures to display per row.

    Returns:
        Formatted rhythm + TAB string.
    """
    SLOT_W = 3  # characters per grid slot

    if not assigned:
        slots = beats_per_measure * 2  # assume eighth-note grid
        mw = slots * SLOT_W + 1  # +1 for padding char
        names = ["G", "D", "A", "E"]
        lines = [f"\u2669={int(bpm)}", ""]
        lines.append(" |" + " " * mw + "|")
        lines.append(" |" + " " * mw + "|")
        for n in names:
            lines.append(f"{n}|" + "-" * mw + "|")
        return "\n".join(lines)

    # --- Determine display strings ---
    max_string = max(an.position.string_number for an in assigned)
    display_strings = [1, 2, 3, 4, 5] if max_string >= 5 else [1, 2, 3, 4]

    # --- Convert notes to beat-space and group simultaneous notes ---
    beat_events: list[tuple[float, float, int, int]] = []
    for an in sorted(assigned, key=lambda a: a.event.start_time):
        s_beat = an.event.start_time * bpm / 60.0
        dur = (an.event.end_time - an.event.start_time) * bpm / 60.0
        beat_events.append((s_beat, dur, an.position.string_number, an.position.fret))

    # Group notes with same start time
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

    # --- Build timeline with rests ---
    timeline: list[tuple[str, float, dict[int, int]]] = []  # (sym, beats, frets)
    current_beat = 0.0

    for start, dur, sym, frets in groups:
        gap = start - current_beat
        if gap > 0.12:
            for r_sym, r_beats in _decompose_duration(gap):
                timeline.append((r_sym + "r", r_beats, {}))
            current_beat = start
        timeline.append((sym, dur, frets))
        current_beat = start + dur

    # --- Determine grid resolution ---
    all_durations = [t[1] for t in timeline]
    grid_beat = min(all_durations) if all_durations else 0.5
    # Ensure grid_beat divides cleanly into beats_per_measure
    slots_per_measure = max(1, round(beats_per_measure / grid_beat))
    # Recalculate grid_beat for consistency
    grid_beat = beats_per_measure / slots_per_measure

    # --- Split timeline into measures ---
    measures: list[list[_MeasureEvent]] = []
    m_events: list[_MeasureEvent] = []
    m_slots_used = 0

    for sym, beats, frets in timeline:
        slots = max(1, round(beats / grid_beat))
        remaining = slots

        while remaining > 0:
            space = slots_per_measure - m_slots_used
            take = min(remaining, space)

            # Determine rhythm symbol for this chunk
            if take == slots:
                chunk_sym = sym
            else:
                chunk_beats = take * grid_beat
                cs, _ = _snap_rhythm(chunk_beats)
                is_rest = sym.endswith("r")
                chunk_sym = cs + ("r" if is_rest else "")

            m_events.append(_MeasureEvent(
                rhythm=chunk_sym, grid_slots=take, frets=frets if not sym.endswith("r") else {},
            ))
            m_slots_used += take
            remaining -= take

            if m_slots_used >= slots_per_measure:
                measures.append(m_events)
                m_events = []
                m_slots_used = 0

    # Flush remaining events, pad with rest
    if m_events:
        space = slots_per_measure - m_slots_used
        if space > 0:
            rest_beats = space * grid_beat
            parts = _decompose_duration(rest_beats)
            for rs, rb in parts:
                rslots = max(1, round(rb / grid_beat))
                m_events.append(_MeasureEvent(rhythm=rs + "r", grid_slots=rslots))
        measures.append(m_events)

    # --- Render ---
    measure_content_w = slots_per_measure * SLOT_W  # chars of note content per measure
    out: list[str] = [f"\u2669={int(bpm)}"]

    for row_start in range(0, len(measures), measures_per_line):
        row_ms = measures[row_start: row_start + measures_per_line]
        out.append("")

        num_parts: list[str] = []
        rhythm_parts: list[str] = []
        tab_parts: dict[int, list[str]] = {s: [] for s in display_strings}

        for m_off, measure in enumerate(row_ms):
            m_num = row_start + m_off + 1

            # Measure number: leading space (padding) + number left-justified
            num_parts.append(" " + str(m_num).ljust(measure_content_w))

            # Rhythm and TAB content for this measure
            r_chars: list[str] = [" "]  # leading padding space
            t_chars: dict[int, list[str]] = {s: ["-"] for s in display_strings}

            for ev in measure:
                w = ev.grid_slots * SLOT_W
                r_chars.append(ev.rhythm.ljust(w))
                for s in display_strings:
                    if s in ev.frets:
                        f_str = str(ev.frets[s])
                        t_chars[s].append(f_str + "-" * (w - len(f_str)))
                    else:
                        t_chars[s].append("-" * w)

            rhythm_parts.append("".join(r_chars))
            for s in display_strings:
                tab_parts[s].append("".join(t_chars[s]))

        # Assemble rows with | separators
        out.append(" |" + "|".join(num_parts) + "|")
        out.append(" |" + "|".join(rhythm_parts) + "|")
        for s in display_strings:
            name = _STRING_NAMES[s]
            out.append(f"{name}|" + "|".join(tab_parts[s]) + "|")

    return "\n".join(out)


def midi_to_tab(config: TabConfig) -> str:
    """Full pipeline: MIDI file → plain-text TAB string.

    Args:
        config: TAB engine configuration.

    Returns:
        The formatted TAB string.

    Raises:
        TabEngineError: If any step in the pipeline fails.
    """
    logger.info("Generating TAB from: {}", config.input_path)

    notes = load_midi_notes(config.input_path)
    if not notes:
        logger.warning("No notes found in MIDI file")

    bpm = detect_bpm(config.input_path)
    logger.info("Detected BPM: {}", int(bpm))

    assigned = assign_positions(notes, config.strategy, config.bass)
    tab = format_tab(assigned, bpm=bpm)

    output_path = config.output_dir / "bass_tab.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tab, encoding="utf-8")
    logger.info("TAB saved to: {}", output_path)

    from src.musicxml_export import export_musicxml
    xml_path = config.output_dir / "bass_tab.xml"
    export_musicxml(assigned, bpm=bpm, output_path=xml_path)
    logger.info("MusicXML saved to: {}", xml_path)

    return tab

"""Module 4: MIDI to bass TAB conversion engine."""

from __future__ import annotations

import math
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

# String display order: G, D, A, E (string numbers 1-4)
_STRING_NAMES = {1: "G", 2: "D", 3: "A", 4: "E"}


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
        bass: Bass configuration. Defaults to standard 4-string tuning.

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
            raise TabEngineError(
                f"MIDI pitch {note.midi_pitch} cannot be played on this bass "
                f"(valid range: {bass.tuning[-1].open_midi}-"
                f"{bass.tuning[0].open_midi + bass.max_fret})"
            )

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


def format_tab(
    assigned: list[AssignedNote],
    beats_per_measure: int = 8,
) -> str:
    """Format assigned notes as a plain-text bass TAB string.

    Notes are quantized into beat slots based on their start_time.
    Each beat slot is one character wide (or wider for fret numbers >= 10).

    Args:
        assigned: List of AssignedNote sorted by start_time.
        beats_per_measure: Number of beat slots per measure.

    Returns:
        Multi-line TAB string with G/D/A/E lines.
    """
    if not assigned:
        # Return empty measure
        dash = "-" * beats_per_measure
        lines = [f"{name}|{dash}|" for name in ["G", "D", "A", "E"]]
        return "\n".join(lines)

    # Determine time resolution: use the smallest time gap between notes,
    # or default to 0.5s if all notes are simultaneous
    sorted_notes = sorted(assigned, key=lambda a: a.event.start_time)

    time_gaps = []
    for i in range(1, len(sorted_notes)):
        gap = sorted_notes[i].event.start_time - sorted_notes[i - 1].event.start_time
        if gap > 1e-6:
            time_gaps.append(gap)

    beat_duration = min(time_gaps) if time_gaps else 0.5

    # Quantize each note to a beat slot index
    min_time = sorted_notes[0].event.start_time
    slot_map: dict[int, dict[int, int]] = {}  # slot_index -> {string_number: fret}

    for an in sorted_notes:
        slot = round((an.event.start_time - min_time) / beat_duration)
        if slot not in slot_map:
            slot_map[slot] = {}
        slot_map[slot][an.position.string_number] = an.position.fret

    total_slots = max(slot_map.keys()) + 1 if slot_map else 0

    # Build measures
    # Pad total_slots to a multiple of beats_per_measure
    num_measures = max(1, math.ceil(total_slots / beats_per_measure))
    total_slots_padded = num_measures * beats_per_measure

    # Build string lines: {string_number: list_of_characters}
    string_lines: dict[int, list[str]] = {s: [] for s in [1, 2, 3, 4]}

    for slot in range(total_slots_padded):
        # Add measure bar at the start of each measure
        if slot % beats_per_measure == 0 and slot > 0:
            for s in string_lines:
                string_lines[s].append("|")

        for s in string_lines:
            if slot in slot_map and s in slot_map[slot]:
                fret_num = slot_map[slot][s]
                string_lines[s].append(str(fret_num))
            else:
                string_lines[s].append("-")

    # Assemble output lines in G, D, A, E order
    output_lines: list[str] = []
    for string_num in [1, 2, 3, 4]:
        name = _STRING_NAMES[string_num]
        content = "".join(string_lines[string_num])
        output_lines.append(f"{name}|{content}|")

    return "\n".join(output_lines)


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

    assigned = assign_positions(notes, config.strategy, config.bass)
    tab = format_tab(assigned)

    output_path = config.output_dir / "bass_tab.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tab, encoding="utf-8")
    logger.info("TAB saved to: {}", output_path)

    return tab

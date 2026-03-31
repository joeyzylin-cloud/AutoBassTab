"""Data models for AutoBassTab."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Strategy(Enum):
    """Fingering assignment strategy."""

    LOWEST_POSITION = "lowest_position"
    MIN_MOVEMENT = "min_movement"
    OPEN_STRING_PREFER = "open_string_prefer"


@dataclass(frozen=True)
class StringTuning:
    """A single bass string's tuning info."""

    string_number: int  # 1=G (thinnest) .. 5=B (thickest)
    name: str
    open_midi: int  # MIDI note number for open string


# Standard 5-string bass tuning
STANDARD_TUNING: tuple[StringTuning, ...] = (
    StringTuning(string_number=1, name="G", open_midi=43),
    StringTuning(string_number=2, name="D", open_midi=38),
    StringTuning(string_number=3, name="A", open_midi=33),
    StringTuning(string_number=4, name="E", open_midi=28),
    StringTuning(string_number=5, name="B", open_midi=23),
)

MAX_FRET = 24


@dataclass(frozen=True)
class FretPosition:
    """A position on the bass fretboard.

    Attributes:
        string_number: 1-5 (1=G, 4=E, 5=B).
        fret: 0-24 (0=open string).
    """

    string_number: int
    fret: int

    def __post_init__(self) -> None:
        """Validate string number and fret range."""
        if not 1 <= self.string_number <= 5:
            raise ValueError(
                f"string_number must be 1-5, got {self.string_number}"
            )
        if not 0 <= self.fret <= MAX_FRET:
            raise ValueError(f"fret must be 0-{MAX_FRET}, got {self.fret}")


@dataclass(frozen=True)
class NoteEvent:
    """A single note extracted from MIDI.

    Attributes:
        midi_pitch: MIDI note number (e.g. 40 = E2).
        start_time: Note onset in seconds.
        end_time: Note release in seconds.
        velocity: MIDI velocity (0-127).
    """

    midi_pitch: int
    start_time: float
    end_time: float
    velocity: int = 100


@dataclass(frozen=True)
class AssignedNote:
    """A NoteEvent with its assigned fretboard position."""

    event: NoteEvent
    position: FretPosition


@dataclass
class BassConfig:
    """Bass guitar configuration.

    Attributes:
        tuning: Tuple of StringTuning, ordered by string number.
        max_fret: Maximum fret number.
    """

    tuning: tuple[StringTuning, ...] = field(default_factory=lambda: STANDARD_TUNING)
    max_fret: int = MAX_FRET

    def midi_to_positions(self, midi_pitch: int) -> list[FretPosition]:
        """Return all valid fretboard positions for a given MIDI pitch.

        Positions are sorted by (fret, string_number) ascending.

        Args:
            midi_pitch: The MIDI note number to map.

        Returns:
            List of FretPosition where this note can be played.
            Empty list if the note is out of range.
        """
        positions: list[FretPosition] = []
        for s in self.tuning:
            fret = midi_pitch - s.open_midi
            if 0 <= fret <= self.max_fret:
                positions.append(FretPosition(string_number=s.string_number, fret=fret))
        positions.sort(key=lambda p: (p.fret, p.string_number))
        return positions


@dataclass
class DownloadConfig:
    """Configuration for the YouTube downloader module."""

    url: str
    output_dir: Path = field(default_factory=lambda: Path("output"))
    audio_format: str = "wav"


@dataclass
class SeparationConfig:
    """Configuration for the audio separation module."""

    input_path: Path
    output_dir: Path = field(default_factory=lambda: Path("output"))
    model_name: str = "htdemucs"


@dataclass
class TranscribeConfig:
    """Configuration for the pitch transcription module."""

    input_path: Path
    output_dir: Path = field(default_factory=lambda: Path("output"))
    # Bass guitar frequency range: low B0 (~31 Hz) to fret-24 on G string (~392 Hz)
    minimum_frequency: float = 30.0
    maximum_frequency: float = 400.0
    # Raise onset/frame thresholds to reduce drum bleed false positives
    onset_threshold: float = 0.5
    frame_threshold: float = 0.4
    # 100 ms filters kick/snare transients; still catches 16th notes at 120 BPM (125 ms)
    minimum_note_length: float = 100.0
    # Octave-shift trick: shift audio up N semitones before transcription so
    # basic-pitch operates in its accurate mid-frequency range, then shift MIDI back.
    # 12 = 1 octave (recommended); 0 = disabled.
    octave_shift: int = 12
    # Path to no_bass / drums stem for transient ducking (optional).
    # When set, kick drum transients are used to duck the bass stem before transcription.
    no_bass_path: Path | None = None


@dataclass
class TabConfig:
    """Configuration for the TAB engine module."""

    input_path: Path
    output_dir: Path = field(default_factory=lambda: Path("output"))
    strategy: Strategy = Strategy.LOWEST_POSITION
    bass: BassConfig = field(default_factory=BassConfig)


# Custom exceptions for each module
class DownloadError(Exception):
    """Raised when YouTube download fails."""


class SeparationError(Exception):
    """Raised when audio separation fails."""


class TranscribeError(Exception):
    """Raised when pitch transcription fails."""


class TabEngineError(Exception):
    """Raised when TAB generation fails."""

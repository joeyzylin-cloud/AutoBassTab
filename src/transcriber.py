"""Module 3: Pitch transcription using basic-pitch."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from loguru import logger
from scipy.signal import butter, sosfilt

from src.models import TranscribeConfig, TranscribeError


def _to_mono(audio: np.ndarray) -> np.ndarray:
    return audio.mean(axis=1) if audio.ndim == 2 else audio


def _lowpass(audio: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    sos = butter(8, cutoff_hz / (sr / 2), btype="low", output="sos")
    if audio.ndim == 1:
        return sosfilt(sos, audio)
    return np.stack([sosfilt(sos, audio[:, ch]) for ch in range(audio.shape[1])], axis=1)


def _apply_transient_ducking(
    bass: np.ndarray,
    sr: int,
    no_bass_path: Path,
    duck_amount: float = 0.85,
) -> np.ndarray:
    """Reduce bass volume at moments when kick drum transients are detected.

    Uses the no_bass stem (already produced by Demucs) filtered to <100 Hz
    to reconstruct a kick-drum energy envelope, then applies sidechain ducking.
    """
    no_bass_audio, nb_sr = sf.read(str(no_bass_path))
    kick_mono = _to_mono(no_bass_audio)
    # Extract kick-drum envelope: low-pass at 100 Hz, then full-wave rectify + smooth
    kick_lp = sosfilt(butter(4, 100.0 / (nb_sr / 2), btype="low", output="sos"), kick_mono)
    kick_env = np.abs(kick_lp)
    # Smooth with a short window (~10 ms) to create a gain envelope
    smooth_samples = max(1, int(nb_sr * 0.010))
    kick_env = np.convolve(kick_env, np.ones(smooth_samples) / smooth_samples, mode="same")
    kick_env /= kick_env.max() + 1e-10  # normalise 0-1

    # Resample envelope to match bass audio length
    if len(kick_env) != len(_to_mono(bass)):
        from scipy.signal import resample
        kick_env = resample(kick_env, len(_to_mono(bass)))

    gain = np.clip(1.0 - kick_env * duck_amount, 0.05, 1.0)
    ducked = bass * (gain[:, np.newaxis] if bass.ndim == 2 else gain)
    logger.info("Transient ducking applied (duck={:.0%}, using {})", duck_amount, no_bass_path.name)
    return ducked


def transcribe_to_midi(config: TranscribeConfig) -> Path:
    """Transcribe an audio file to MIDI using basic-pitch.

    Pipeline:
      1. Low-pass filter  — remove frequencies above bass range
      2. Transient ducking — suppress kick-drum bleed using no_bass stem (opt.)
      3. Octave-shift up  — move audio into basic-pitch's accurate frequency band
      4. basic-pitch inference
      5. Shift MIDI back  — restore original octave
      6. Pitch correction — fix systematic 1-semitone bias on open strings

    Returns:
        Path to the generated MIDI file (bass_track.mid).
    """
    try:
        from basic_pitch.inference import predict
    except ImportError as e:
        raise TranscribeError(
            "basic-pitch is not installed. "
            "Install with: pip install autobass[pipeline]"
        ) from e

    if not config.input_path.exists():
        raise TranscribeError(f"Input file not found: {config.input_path}")

    # Force TF determinism
    import os
    os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
    os.environ.setdefault("PYTHONHASHSEED", "42")
    try:
        import tensorflow as tf
        tf.random.set_seed(42)
    except Exception:
        pass

    logger.info("Transcribing audio to MIDI: {}", config.input_path)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.output_dir / "bass_track.mid"

    audio, sr = sf.read(str(config.input_path))

    # ── Step 1: Low-pass filter ──────────────────────────────────────────────
    cutoff_hz = min(500.0, config.maximum_frequency * 1.25)
    audio = _lowpass(audio, sr, cutoff_hz)
    logger.info("Low-pass filter at {:.0f} Hz applied", cutoff_hz)

    # ── Step 2: Transient ducking (optional) ────────────────────────────────
    if config.no_bass_path and config.no_bass_path.exists():
        audio = _apply_transient_ducking(audio, sr, config.no_bass_path)
    else:
        logger.info("Transient ducking skipped (no_bass_path not set)")

    # ── Step 3: Octave-shift up ──────────────────────────────────────────────
    n_shift = config.octave_shift
    freq_mult = 2 ** (n_shift / 12)
    if n_shift > 0:
        import librosa
        logger.info("Octave-shift: +{} semitones (×{:.2f} frequency) before transcription", n_shift, freq_mult)
        audio_mono = _to_mono(audio)
        audio_shifted = librosa.effects.pitch_shift(audio_mono.astype(np.float32), sr=sr, n_steps=n_shift)
        shifted_path = config.output_dir / "bass_shifted.wav"
        sf.write(str(shifted_path), audio_shifted, sr)
        transcribe_input = shifted_path
    else:
        filtered_path = config.output_dir / "bass_filtered.wav"
        sf.write(str(filtered_path), audio, sr)
        transcribe_input = filtered_path

    # ── Step 4: basic-pitch inference ───────────────────────────────────────
    logger.info(
        "basic-pitch — freq: {:.0f}–{:.0f} Hz, onset: {}, frame: {}, min_note: {} ms",
        config.minimum_frequency * freq_mult,
        config.maximum_frequency * freq_mult,
        config.onset_threshold,
        config.frame_threshold,
        config.minimum_note_length,
    )
    try:
        _, midi_data, _ = predict(
            str(transcribe_input),
            onset_threshold=config.onset_threshold,
            frame_threshold=config.frame_threshold,
            minimum_note_length=config.minimum_note_length,
            minimum_frequency=config.minimum_frequency * freq_mult,
            maximum_frequency=config.maximum_frequency * freq_mult,
        )
    except Exception as e:
        raise TranscribeError(f"basic-pitch inference failed: {e}") from e

    # ── Step 5: Shift MIDI notes back down ──────────────────────────────────
    if n_shift > 0:
        for inst in midi_data.instruments:
            for note in inst.notes:
                note.pitch = max(0, note.pitch - n_shift)
        logger.info("MIDI notes shifted back down {} semitones", n_shift)

    # ── Step 6: Pitch correction ─────────────────────────────────────────────
    # basic-pitch still has a slight upward bias on open-string notes; snap
    # any sub-C2 note down 1 semitone if it lands on an open bass string.
    OPEN_STRINGS = {23, 28, 33, 38, 43}  # B0 E1 A1 D2 G2
    corrections = 0
    for inst in midi_data.instruments:
        for note in inst.notes:
            if note.pitch < 36 and (note.pitch - 1) in OPEN_STRINGS:
                note.pitch -= 1
                corrections += 1
    if corrections:
        logger.info("Pitch correction: {} notes snapped to nearest open string", corrections)

    midi_data.write(str(output_path))
    note_count = sum(len(inst.notes) for inst in midi_data.instruments)
    logger.info("MIDI saved to: {} ({} notes)", output_path, note_count)
    return output_path

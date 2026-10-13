# AutoBassTab

Turn a YouTube link into bass guitar TAB. AutoBassTab downloads the audio, isolates the bass line, transcribes it to MIDI, and then works out string and fret positions to produce a plain-text TAB and a MusicXML file you can open in MuseScore.

It can be used from the command line or through a small local web app.

## How it works

The pipeline has four stages:

| # | Module | What it does | Output |
|---|--------|--------------|--------|
| 1 | `src/downloader.py` | Downloads the audio from YouTube with **yt-dlp** | `audio_full.wav` |
| 2 | `src/separator.py` | Splits out the bass with **Demucs** (`htdemucs`, two-stem bass mode) | `bass_only.wav`, `no_bass.wav` |
| 3 | `src/transcriber.py` | Detects pitches with **basic-pitch** after three preprocessing steps | `bass_track.mid` |
| 4 | `src/tab_engine.py` | Converts MIDI to TAB, detects BPM, exports MusicXML | `bass_tab.txt`, `bass_tab.xml` |

### Transcription details

Bass notes are very low, which is hard for pitch detectors. The transcriber works around this in three steps before running basic-pitch:

1. **Low-pass filter** (Butterworth, 500 Hz cutoff) removes non-bass frequencies.
2. **Sidechain-style ducking** uses the low end of the `no_bass` stem to find kick drum hits and lowers the bass stem at those moments, reducing kick bleed.
3. **Octave-up trick:** the audio is pitch-shifted up 12 semitones, since basic-pitch is more accurate in higher registers. Every detected note is shifted back down 12 semitones afterward.

After transcription, TensorFlow runs in deterministic mode (fixed seed) so repeated runs give the same result, and notes below C2 that sit one semitone above an open string are snapped down to it.

### Fingering strategies

The TAB engine assumes a standard 5-string bass (B-E-A-D-G, frets 0-24). If no note lands on the B string, only four lines are printed.

| Strategy | Behavior |
|----------|----------|
| `lowest_position` (default) | Lowest fret available; ties go to the lowest string number |
| `min_movement` | Closest position to the previous note |
| `open_string_prefer` | Uses an open string when possible, otherwise falls back to `lowest_position` |

### Output format

TAB is printed with a rhythm row above each staff and bar numbers:

```
♩=120

 | 1                   | 2                   |
 | Q.r    S  E     Q   | E     Q.            |
G|-------5--14----0----|--0---10-------------|
D|-3-------------------|---------------------|
A|---------------------|---------------------|
E|---------------------|---------------------|
```

Rhythm symbols: `W` whole, `H` half, `Q` quarter, `E` eighth, `S` sixteenth, `.` dotted, `r` rest.

## Requirements

- **Python 3.11** (3.12 and newer are not compatible with TensorFlow / basic-pitch)
- ffmpeg available on your PATH (needed by yt-dlp and Demucs for audio conversion)

Python packages used by the project: `loguru`, `pretty-midi`, `yt-dlp`, `demucs`, `basic-pitch`, `librosa`, `scipy`, `flask` (web UI), and `pytest` (tests).

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install loguru pretty-midi yt-dlp demucs basic-pitch librosa scipy flask pytest
```

## Usage

### Command line

```bash
# Full pipeline
python main.py "https://youtu.be/..."

# Pick a fingering strategy
python main.py --strategy min_movement "https://youtu.be/..."

# Resume from an existing MIDI file (skip stages 1-3)
python main.py --skip-download --skip-separate --skip-transcribe output/bass_track.mid
```

Options:

| Flag | Description |
|------|-------------|
| `input` | YouTube URL, or a file path when a `--skip-*` flag is used |
| `-o`, `--output-dir` | Output directory (default `./output`) |
| `-s`, `--strategy` | `lowest_position`, `min_movement`, or `open_string_prefer` |
| `--skip-download` | Skip stage 1; input is an audio file |
| `--skip-separate` | Skip stage 2; input is an isolated bass audio file |
| `--skip-transcribe` | Skip stage 3; input is a MIDI file |
| `--demucs-model` | Demucs model name (default `htdemucs`) |

The TAB is printed to the terminal and saved to `output/bass_tab.txt`.

### Web app

```bash
python web_app.py
```

Open http://localhost:5000, paste a YouTube URL, choose a strategy, and watch live progress while the job runs. When it finishes, the TAB is shown in color in the browser and the MusicXML file can be downloaded. Each job writes to its own folder under `output/`.

### Viewing the MusicXML

`bass_tab.xml` is MusicXML 3.1 with a TAB clef and tempo marking. Open it in [MuseScore 4](https://musescore.org) (free) to see standard notation together with the TAB.

## Project layout

```
main.py                CLI entry point
web_app.py             Flask server with live progress (SSE)
templates/index.html   Web UI
src/
  models.py            Dataclasses and enums (configs, strategies)
  downloader.py        Stage 1: yt-dlp
  separator.py         Stage 2: Demucs
  transcriber.py       Stage 3: basic-pitch + preprocessing
  tab_engine.py        Stage 4: MIDI -> TAB, BPM detection
  musicxml_export.py   MusicXML export
  utils.py             Shared helpers (e.g. directory creation)
tests/
  test_models.py
  test_tab_engine.py
output/                Generated files, one folder per web job (gitignored)
```

## Tests

```bash
pytest tests/ -v
```

## Limitations

- Accuracy depends on how cleanly Demucs can isolate the bass; dense mixes and heavy kick drums can still produce wrong or extra notes.
- Fingering is chosen by simple rules, not by what is comfortable or idiomatic to play, so review the result before relying on it.
- Only works with audio you are allowed to download and process.

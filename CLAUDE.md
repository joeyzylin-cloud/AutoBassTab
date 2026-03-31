# AutoBassTab

YouTube 音訊 → 貝斯 TAB 譜 + MusicXML 的 CLI / Web 工具。

## Architecture

四模組管線：
1. `downloader.py` — yt-dlp 下載 YouTube → `audio_full.wav`
2. `separator.py` — Demucs (`htdemucs`, `--two-stems bass`) → `bass_only.wav` + `no_bass.wav`
3. `transcriber.py` — basic-pitch 音高辨識 → `bass_track.mid`（含三層前處理）
4. `tab_engine.py` — MIDI → 純文字 TAB 譜 + MusicXML

Web 介面：
- `web_app.py` — Flask SSE server，即時進度條
- `templates/index.html` — 單頁前端，彩色 TAB 顯示、MusicXML 下載

## Tech Stack & Conventions

- Python 3.11（3.12/3.14 與 tensorflow/basic-pitch 不相容）
- `.venv/` in project root（Python 3.11.9）
- dataclass for data structures, Path objects, Enum for fixed options
- loguru for logging（no bare print）
- pytest for tests
- Each module has custom Exception

## Bass Domain Knowledge

五弦標準調音 (MIDI):
- 1弦 G = 43, 2弦 D = 38, 3弦 A = 33, 4弦 E = 28, 5弦 B = 23
- Fret range: 0–24
- 預設用五弦計算；輸出時若無 B 弦音符則只印 G/D/A/E 四行

## Tab Engine Strategies

- `LOWEST_POSITION`: 最小 fret，同 fret 選最小弦號
- `MIN_MOVEMENT`: 與前一音最近位置，首音用 LOWEST_POSITION
- `OPEN_STRING_PREFER`: fret=0 優先，否則 fallback LOWEST_POSITION

## Tab Output Format（雙層）

```
♩=120

 | 1                   | 2                   |
 | Q.r    S  E     Q   | E     Q.            |
G|-------5--14----0----|--0---10-------------|
D|-3-------------------|---------------------|
A|---------------------|---------------------|
E|---------------------|---------------------|
```

- 第一行：BPM header（`♩=120`）
- 節奏行前綴 ` |`，TAB 行前綴 `X|`
- 每個 grid slot = 3 chars，最短音符 = 1 slot
- 節奏符號：W H Q E S（全半四八十六分）、`.` 附點、`r` 休止
- 小節號行：` | 1   | 2   |`

## Transcription Pipeline (Module 3)

三層前處理，按順序執行：

1. **低通濾波** — scipy `butter(8)` 截止 500 Hz，濾掉非貝斯頻率
2. **側鏈壓縮** — 用 `no_bass.wav` 100 Hz 以下能量偵測踢鼓時間點，對 bass stem 做 ducking（duck=85%），減少踢鼓基頻滲漏
3. **升八度欺騙** — `librosa.effects.pitch_shift` 上移 12 semitones；basic-pitch 在中高頻精準度遠高於極低頻；transcribe 後 MIDI 音符全部 -12 還原

後處理：
- TF determinism（`TF_DETERMINISTIC_OPS=1`，seed=42）確保每次結果相同
- 低頻音符偏差修正：sub-C2 音符若 -1 semitone 落在空弦（B0/E1/A1/D2/G2）則自動 snap down

Key params in `TranscribeConfig`:
- `minimum_frequency=30.0`, `maximum_frequency=400.0` — 貝斯頻率範圍
- `onset_threshold=0.5`, `frame_threshold=0.4`
- `minimum_note_length=100.0` ms — 濾掉鼓的短暫衝擊
- `octave_shift=12` — 升八度 semitones（0 = 停用）
- `no_bass_path` — Demucs no_bass stem 路徑（供側鏈壓縮使用）

## MusicXML Export

`src/musicxml_export.py` — `export_musicxml(assigned, bpm, output_path)`

- 輸出 MusicXML 3.1 Partwise 格式（`bass_tab.xml`）
- TAB clef，4 或 5 弦 staff-details，含速度標記
- 可用 MuseScore 4（免費）開啟，顯示完整五線譜＋TAB

## Commands

```bash
# CLI — full pipeline
python main.py "https://youtu.be/..."

# CLI — skip steps
python main.py --skip-download --skip-separate --skip-transcribe output/bass_track.mid
python main.py --strategy min_movement "https://youtu.be/..."

# Web UI
python web_app.py   # → http://localhost:5000

# Tests
pytest tests/ -v    # 51 tests
```

## Key Files

```
src/
  models.py          — dataclasses: BassConfig, TranscribeConfig, TabConfig, etc.
  downloader.py      — Module 1: yt-dlp
  separator.py       — Module 2: Demucs subprocess
  transcriber.py     — Module 3: basic-pitch + 3-layer preprocessing
  tab_engine.py      — Module 4: MIDI → TAB, BPM detection, format_tab()
  musicxml_export.py — MusicXML export
web_app.py           — Flask web server
templates/index.html — Web UI
tests/
  test_models.py
  test_tab_engine.py
output/              — per-job subdirectories (gitignored)
.venv/               — Python 3.11 venv (gitignored)
```

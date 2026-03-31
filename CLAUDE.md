# AutoBassTab

YouTube 音訊 → 貝斯 TAB 譜的 CLI 工具。

## Architecture

四模組管線：
1. `downloader.py` — yt-dlp 下載 YouTube → audio_full.wav
2. `separator.py` — Demucs 音軌分離 → bass_only.wav
3. `transcriber.py` — basic-pitch 音高辨識 → bass_track.mid
4. `tab_engine.py` — MIDI → 純文字 TAB 譜（完整實作）

Module 1-3 需要 GPU/網路，目前只有介面 stub。
Module 4 是純邏輯，可完整測試。

## Tech Stack & Conventions

- Python 3.11+, type hints + docstring on all functions
- dataclass for data structures (no raw dict)
- Path objects for file paths (no strings)
- Enum for fixed options
- loguru for logging (no bare print)
- pytest for tests
- Each module has custom Exception

## Bass Domain Knowledge

五弦標準調音 (MIDI):
- 1弦 G = 43, 2弦 D = 38, 3弦 A = 33, 4弦 E = 28, 5弦 B = 23
- Fret range: 0-24
- 預設用五弦計算指法；輸出時若無音符用到 B 弦則只印 G/D/A/E 四行

## Tab Engine Strategies

- LOWEST_POSITION: 最小 fret，同 fret 選最小弦號
- MIN_MOVEMENT: 與前一音最近位置，首音用 LOWEST_POSITION
- OPEN_STRING_PREFER: fret=0 優先，否則 fallback LOWEST_POSITION

## Tab Output Format

四弦（未用到 B 弦）：
```
G|--------|--------|
D|--------|--------|
A|-0---5--|--------|
E|--------|--0--3--|
```

五弦（有用到 B 弦）：
```
G|--------|--------|
D|--------|--------|
A|-0---5--|--------|
E|--------|--0--3--|
B|--2-----|--------|
```

## Commands

- `python main.py <youtube_url>` — full pipeline
- `python main.py --skip-download --skip-separate --skip-transcribe bass_track.mid` — tab only
- `pytest tests/ -v` — run tests

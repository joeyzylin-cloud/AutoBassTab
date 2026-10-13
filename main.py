"""AutoBassTab CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from src.models import (
    DownloadConfig,
    SeparationConfig,
    Strategy,
    TabConfig,
    TranscribeConfig,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list. Defaults to sys.argv[1:].

    Returns:
        Parsed namespace with all CLI options.
    """
    parser = argparse.ArgumentParser(
        prog="autobass",
        description="Convert YouTube audio to bass TAB notation.",
    )
    parser.add_argument(
        "input",
        help="YouTube URL or path to audio/MIDI file (depending on --skip flags).",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory (default: ./output).",
    )
    parser.add_argument(
        "-s", "--strategy",
        type=str,
        choices=[s.value for s in Strategy],
        default=Strategy.LOWEST_POSITION.value,
        help="Fingering strategy (default: lowest_position).",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip Module 1. Input should be an audio file path.",
    )
    parser.add_argument(
        "--skip-separate",
        action="store_true",
        help="Skip Module 2. Input should be an isolated bass audio file path.",
    )
    parser.add_argument(
        "--skip-transcribe",
        action="store_true",
        help="Skip Module 3. Input should be a MIDI file path.",
    )
    parser.add_argument(
        "--demucs-model",
        type=str,
        default="htdemucs",
        help="Demucs model name (default: htdemucs).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the AutoBassTab pipeline.

    Args:
        argv: Optional argument list for testing. Defaults to sys.argv[1:].
    """
    args = parse_args(argv)
    output_dir = args.output_dir
    strategy = Strategy(args.strategy)
    current_path: Path | str = args.input

    logger.info("AutoBassTab starting — strategy: {}", strategy.value)

    # Module 1: Download
    if not args.skip_download:
        from src.downloader import download_audio

        config = DownloadConfig(url=str(current_path), output_dir=output_dir)
        current_path = download_audio(config)
        logger.info("Download complete: {}", current_path)
    else:
        current_path = Path(current_path)
        logger.info("Skipping download, using: {}", current_path)

    # Module 2: Separate
    no_bass_path: Path | None = None
    if not args.skip_separate:
        from src.separator import separate_bass

        config = SeparationConfig(
            input_path=Path(current_path),
            output_dir=output_dir,
            model_name=args.demucs_model,
        )
        current_path = separate_bass(config)
        logger.info("Separation complete: {}", current_path)
        # Demucs also writes the no_bass stem, used for kick-drum ducking in Module 3
        no_bass_path = (
            output_dir / "separated" / args.demucs_model / config.input_path.stem / "no_bass.wav"
        )
    else:
        logger.info("Skipping separation, using: {}", current_path)

    # Module 3: Transcribe
    if not args.skip_transcribe:
        from src.transcriber import transcribe_to_midi

        config = TranscribeConfig(
            input_path=Path(current_path),
            output_dir=output_dir,
            no_bass_path=no_bass_path if no_bass_path and no_bass_path.exists() else None,
        )
        current_path = transcribe_to_midi(config)
        logger.info("Transcription complete: {}", current_path)
    else:
        logger.info("Skipping transcription, using: {}", current_path)

    # Module 4: TAB generation
    from src.tab_engine import midi_to_tab

    tab_config = TabConfig(
        input_path=Path(current_path),
        output_dir=output_dir,
        strategy=strategy,
    )
    tab_output = midi_to_tab(tab_config)

    # Write TAB to file and stdout
    tab_file = output_dir / "bass_tab.txt"
    tab_file.parent.mkdir(parents=True, exist_ok=True)
    tab_file.write_text(tab_output, encoding="utf-8")
    logger.info("TAB written to: {}", tab_file)

    sys.stdout.buffer.write(tab_output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()

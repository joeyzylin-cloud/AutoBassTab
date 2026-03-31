"""AutoBassTab web interface."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from loguru import logger

app = Flask(__name__)

_jobs: dict[str, dict] = {}
_job_local = threading.local()


def _log_sink(message) -> None:
    """Loguru sink: captures log lines for the current job thread."""
    job_id = getattr(_job_local, "job_id", None)
    if job_id and job_id in _jobs:
        _jobs[job_id]["log"].append(str(message).rstrip())


logger.add(_log_sink, format="{level.name}: {message}", level="INFO")


def _run_pipeline(job_id: str, url: str, strategy: str) -> None:
    _job_local.job_id = job_id
    job = _jobs[job_id]
    try:
        from src.downloader import DownloadConfig, download_audio
        from src.models import SeparationConfig, Strategy, TabConfig, TranscribeConfig
        from src.separator import separate_bass
        from src.tab_engine import midi_to_tab
        from src.transcriber import transcribe_to_midi

        out_dir = Path("output") / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        job["step"] = "downloading"
        logger.info("正在下載音訊…")
        wav_path = download_audio(DownloadConfig(url=url, output_dir=out_dir))
        logger.info("下載完成")

        job["step"] = "separating"
        logger.info("正在分離 Bass 音軌（使用 Demucs，可能需要數分鐘）…")
        bass_wav = separate_bass(SeparationConfig(input_path=wav_path, output_dir=out_dir))
        logger.info("音軌分離完成")

        job["step"] = "transcribing"
        logger.info("正在轉錄 MIDI（使用 basic-pitch）…")
        # Find no_bass stem produced by Demucs for transient ducking
        stem_name = wav_path.stem
        no_bass_path = out_dir / "separated" / "htdemucs" / stem_name / "no_bass.wav"
        midi_path = transcribe_to_midi(TranscribeConfig(
            input_path=bass_wav,
            output_dir=out_dir,
            no_bass_path=no_bass_path if no_bass_path.exists() else None,
        ))
        logger.info("MIDI 轉錄完成")

        job["step"] = "generating"
        logger.info("正在生成 TAB 譜…")
        tab = midi_to_tab(TabConfig(
            input_path=midi_path,
            output_dir=out_dir,
            strategy=Strategy(strategy),
        ))

        job["tab"] = tab
        job["xml_path"] = str(out_dir / "bass_tab.xml")
        job["status"] = "done"

    except Exception as exc:
        logger.exception("Pipeline failed for job {}", job_id)
        job["error"] = str(exc)
        job["status"] = "error"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.json or {}
    url = (data.get("url") or "").strip()
    strategy = data.get("strategy", "lowest_position")
    if not url:
        return jsonify({"error": "請輸入 YouTube URL"}), 400

    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "status": "running",
        "step": "starting",
        "log": [],
        "tab": None,
        "xml_path": None,
        "error": None,
    }
    threading.Thread(target=_run_pipeline, args=(job_id, url, strategy), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    """SSE: real-time step + log + completion events."""
    def generate():
        last_idx = 0
        last_step = None
        # Confirm connection immediately
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        while True:
            job = _jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'type': 'error', 'msg': 'Job not found'})}\n\n"
                break

            # Emit step-change event whenever job["step"] changes
            current_step = job.get("step")
            if current_step != last_step:
                yield f"data: {json.dumps({'type': 'step', 'step': current_step})}\n\n"
                last_step = current_step

            # Emit new log lines
            new_logs = job["log"][last_idx:]
            for msg in new_logs:
                yield f"data: {json.dumps({'type': 'log', 'msg': msg})}\n\n"
            last_idx += len(new_logs)

            if job["status"] == "done":
                yield f"data: {json.dumps({'type': 'done', 'tab': job['tab'], 'job_id': job_id})}\n\n"
                break
            elif job["status"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'msg': job.get('error', 'Unknown error')})}\n\n"
                break

            time.sleep(0.3)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download/<job_id>")
def download(job_id: str):
    job = _jobs.get(job_id)
    if not job or not job.get("xml_path"):
        return "Not found", 404
    return send_file(job["xml_path"], as_attachment=True, download_name="bass_tab.xml")


if __name__ == "__main__":
    print("AutoBassTab running at http://localhost:5000")
    app.run(debug=False, port=5000, threaded=True)

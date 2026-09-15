from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import traceback


PRESET = "ARPHE_DIALOGUE_CLEAN_V1"


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def process_audio(source: Path, output: Path, job_path: Path) -> None:
    import av

    state = json.loads(job_path.read_text(encoding="utf-8-sig"))
    state.update(status="RUNNING", progress_percent=0)
    _save(job_path, state)
    source_container = av.open(str(source))
    audio_stream = next((stream for stream in source_container.streams if stream.type == "audio"), None)
    if audio_stream is None:
        raise RuntimeError("Il file sorgente non contiene una traccia audio")

    output.parent.mkdir(parents=True, exist_ok=True)
    destination = av.open(str(output), mode="w")
    output_stream = destination.add_stream("pcm_s16le", rate=48000)
    output_stream.layout = "stereo"
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="stereo", rate=48000)
    graph = None
    source_node = sink = None
    processed = 0
    duration = float(audio_stream.duration * audio_stream.time_base) if audio_stream.duration else 0.0
    try:
        for frame in source_container.decode(audio_stream):
            if graph is None:
                graph = av.filter.Graph()
                source_node = graph.add("abuffer", (
                    f"time_base={frame.time_base}:sample_rate={frame.sample_rate}:"
                    f"sample_fmt={frame.format.name}:channel_layout={frame.layout.name}"
                ))
                highpass = graph.add("highpass", "f=80")
                denoise = graph.add("afftdn", "nr=8:nf=-50:tn=1")
                compressor = graph.add("acompressor", "threshold=0.125:ratio=3:attack=15:release=150:makeup=1.4")
                limiter = graph.add("alimiter", "limit=0.891:attack=5:release=50")
                sink = graph.add("abuffersink")
                source_node.link_to(highpass)
                highpass.link_to(denoise)
                denoise.link_to(compressor)
                compressor.link_to(limiter)
                limiter.link_to(sink)
                graph.configure()
            graph.push(frame)
            while True:
                try:
                    filtered = graph.pull()
                except (av.error.BlockingIOError, av.error.EOFError):
                    break
                for converted in resampler.resample(filtered):
                    for packet in output_stream.encode(converted):
                        destination.mux(packet)
            processed += 1
            if processed % 250 == 0 and duration > 0:
                position = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
                state["progress_percent"] = min(99, int(position / duration * 100))
                _save(job_path, state)
        if graph is not None:
            graph.push(None)
            while True:
                try:
                    filtered = graph.pull()
                except av.error.EOFError:
                    break
                except av.error.BlockingIOError:
                    continue
                for converted in resampler.resample(filtered):
                    for packet in output_stream.encode(converted):
                        destination.mux(packet)
        for converted in resampler.resample(None):
            for packet in output_stream.encode(converted):
                destination.mux(packet)
        for packet in output_stream.encode(None):
            destination.mux(packet)
    finally:
        destination.close()
        source_container.close()

    check = av.open(str(output))
    check_stream = next(stream for stream in check.streams if stream.type == "audio")
    output_duration = float(check_stream.duration * check_stream.time_base) if check_stream.duration else None
    check.close()
    if output_duration is not None and duration and abs(output_duration - duration) > (1 / 30):
        raise RuntimeError(f"Audio non sincronizzato: differenza {output_duration - duration:.3f}s")
    state.update(status="COMPLETED", progress_percent=100, output_path=str(output),
                 output_duration_seconds=output_duration, sample_rate=48000, channels=2)
    _save(job_path, state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    job = Path(args.job)
    try:
        process_audio(Path(args.source), Path(args.output), job)
        return 0
    except Exception as exc:
        state = json.loads(job.read_text(encoding="utf-8-sig")) if job.is_file() else {}
        state.update(status="FAILED", error_type=type(exc).__name__, error=str(exc),
                     diagnostic=traceback.format_exc(limit=4), progress_percent=state.get("progress_percent", 0))
        _save(job, state)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

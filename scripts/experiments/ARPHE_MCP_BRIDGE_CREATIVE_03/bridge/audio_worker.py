from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import traceback


PRESET = "ARPHE_DIALOGUE_CLEAN_V1"
LEVEL_PRESET = "ARPHE_DIALOGUE_LEVEL_V2"
DISTANT_PRESET = "ARPHE_DIALOGUE_DISTANT_V3"
PRESETS = frozenset({PRESET, LEVEL_PRESET, DISTANT_PRESET})


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def process_audio(source: Path, output: Path, job_path: Path, preset: str = PRESET) -> None:
    import av

    if preset not in PRESETS:
        raise ValueError("Preset audio non consentito")

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
                denoise = graph.add(
                    "afftdn",
                    "nr=14:nf=-48:tn=1" if preset == DISTANT_PRESET else "nr=8:nf=-50:tn=1",
                )
                if preset in {LEVEL_PRESET, DISTANT_PRESET}:
                    if preset == DISTANT_PRESET:
                        presence = graph.add("equalizer", "f=3200:t=q:w=1.2:g=3")
                        booster = graph.add("volume", "volume=6dB")
                        level_options = "f=300:g=15:p=0.82:m=8:r=0.16:s=8:t=0.008:o=0.5"
                        compressor_options = "threshold=0.10:ratio=2.5:attack=10:release=180:makeup=1.15"
                    else:
                        presence = None
                        booster = None
                        level_options = "f=400:g=21:p=0.85:m=4:r=0.12:s=6:t=0.01:o=0.5"
                        compressor_options = "threshold=0.125:ratio=2:attack=15:release=150:makeup=1.1"
                    leveler = graph.add(
                        "dynaudnorm",
                        level_options,
                    )
                    compressor = graph.add(
                        "acompressor",
                        compressor_options,
                    )
                else:
                    presence = None
                    booster = None
                    leveler = None
                    compressor = graph.add(
                        "acompressor",
                        "threshold=0.125:ratio=3:attack=15:release=150:makeup=1.4",
                    )
                limiter_options = (
                    "limit=0.8:attack=5:release=50:level=false"
                    if preset == DISTANT_PRESET
                    else "limit=0.891:attack=5:release=50"
                )
                limiter = graph.add("alimiter", limiter_options)
                sink = graph.add("abuffersink")
                source_node.link_to(highpass)
                highpass.link_to(denoise)
                if leveler is not None:
                    if presence is not None:
                        denoise.link_to(presence)
                        presence.link_to(leveler)
                    else:
                        denoise.link_to(leveler)
                    leveler.link_to(compressor)
                else:
                    denoise.link_to(compressor)
                if booster is not None:
                    compressor.link_to(booster)
                    booster.link_to(limiter)
                else:
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
    parser.add_argument("--preset", default=PRESET, choices=sorted(PRESETS))
    args = parser.parse_args()
    job = Path(args.job)
    try:
        process_audio(Path(args.source), Path(args.output), job, args.preset)
        return 0
    except Exception as exc:
        state = json.loads(job.read_text(encoding="utf-8-sig")) if job.is_file() else {}
        state.update(status="FAILED", error_type=type(exc).__name__, error=str(exc),
                     diagnostic=traceback.format_exc(limit=4), progress_percent=state.get("progress_percent", 0))
        _save(job, state)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

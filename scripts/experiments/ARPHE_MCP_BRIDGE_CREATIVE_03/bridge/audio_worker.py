from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import math
import struct
import tempfile
import time
import traceback
import wave

from .audio_provenance import file_sha256, media_fingerprint, silence_windows_sha256


PRESET = "ARPHE_DIALOGUE_CLEAN_V1"
LEVEL_PRESET = "ARPHE_DIALOGUE_LEVEL_V2"
DISTANT_PRESET = "ARPHE_DIALOGUE_DISTANT_V3"
NATURAL_PRESET = "ARPHE_DIALOGUE_NATURAL_V4"
PRESETS = frozenset({PRESET, LEVEL_PRESET, DISTANT_PRESET, NATURAL_PRESET})


SYNC_TOLERANCE_SECONDS = 1 / 30
SILENCE_RMS_THRESHOLD = 0.01
SILENCE_MIN_DURATION_SECONDS = 0.3
SILENCE_ANALYSIS_BLOCK_SAMPLES = 480


@dataclass(frozen=True)
class DecodedAudioClock:
    duration_seconds: float
    start_seconds: float
    end_seconds: float


class _DecodedAudioClockTracker:
    def __init__(self) -> None:
        self.sample_rate: int | None = None
        self.sample_count = 0
        self.start: float | None = None
        self.end: float | None = None

    def observe(self, frame: object) -> None:
        rate = int(frame.sample_rate)
        if rate <= 0 or (self.sample_rate is not None and rate != self.sample_rate):
            raise RuntimeError("Sample rate audio non coerente")
        if frame.pts is None:
            raise RuntimeError("PTS audio non disponibile")
        position = float(frame.pts * frame.time_base)
        frame_end = position + (int(frame.samples) / rate)
        if self.start is None:
            self.start = position
        elif self.end is not None and abs(position - self.end) > SYNC_TOLERANCE_SECONDS:
            raise RuntimeError("Discontinuità PTS audio")
        self.end = frame_end
        self.sample_rate = rate
        self.sample_count += int(frame.samples)

    def finish(self) -> DecodedAudioClock:
        if self.sample_rate is None or self.start is None or self.end is None or self.sample_count <= 0:
            raise RuntimeError("Durata audio decodificata non disponibile")
        duration = self.sample_count / self.sample_rate
        if (abs(self.start) > SYNC_TOLERANCE_SECONDS
                or abs((self.end - self.start) - duration) > SYNC_TOLERANCE_SECONDS):
            raise RuntimeError("Offset o durata PTS audio non verificabile")
        return DecodedAudioClock(duration, self.start, self.end)


def decoded_audio_clock(frames: object) -> DecodedAudioClock:
    """Measure decoded audio by samples and reject PTS discontinuities.

    Container and stream metadata are advisory: Matroska streams may omit a
    duration or include video tail padding.  The decoded samples are the
    authoritative duration for an audio-to-audio sync check.
    """
    tracker = _DecodedAudioClockTracker()
    for frame in frames:
        tracker.observe(frame)
    return tracker.finish()


def detect_silence_windows(path: Path) -> tuple[tuple[float, float], ...]:
    """Return ordered, sample-clocked quiet ranges from the normalized editorial WAV.

    The worker deliberately measures its own 48 kHz stereo PCM output.  That makes
    each reported window reproducible from the hash-bound artefact and avoids
    treating container duration or source-stream timestamps as silence evidence.
    """
    with wave.open(str(path), "rb") as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate(), handle.getcomptype()) != (2, 2, 48_000, "NONE"):
            raise RuntimeError("WAV editoriale non idoneo all'analisi silenzi")
        total_frames = handle.getnframes()
        windows: list[tuple[float, float]] = []
        quiet_start: int | None = None
        position = 0
        while position < total_frames:
            frames = min(SILENCE_ANALYSIS_BLOCK_SAMPLES, total_frames - position)
            data = handle.readframes(frames)
            values = struct.unpack("<" + "h" * (frames * 2), data)
            rms = math.sqrt(sum(sample * sample for sample in values) / len(values)) / 32768
            if rms <= SILENCE_RMS_THRESHOLD:
                if quiet_start is None:
                    quiet_start = position
            elif quiet_start is not None:
                if position - quiet_start >= round(SILENCE_MIN_DURATION_SECONDS * 48_000):
                    windows.append((quiet_start / 48_000, position / 48_000))
                quiet_start = None
            position += frames
        if quiet_start is not None and total_frames - quiet_start >= round(SILENCE_MIN_DURATION_SECONDS * 48_000):
            windows.append((quiet_start / 48_000, total_frames / 48_000))
    return tuple(windows)


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
    if state.get("schema") != "ARPHE_AUDIO_JOB_V2":
        raise ValueError("Manifest audio job V2 richiesto")
    if state.get("preset") != preset:
        raise ValueError("Preset richiesto diverso dal manifest")
    if state.get("source_fingerprint") != media_fingerprint(source):
        raise ValueError("Sorgente audio diversa dal manifest")
    if Path(str(state.get("output_path", ""))).resolve() != output.resolve():
        raise ValueError("Output audio diverso dal manifest")
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
    progress_duration = float(source_container.duration / av.time_base) if source_container.duration else 0.0
    clock = _DecodedAudioClockTracker()
    try:
        for frame in source_container.decode(audio_stream):
            clock.observe(frame)
            if graph is None:
                graph = av.filter.Graph()
                source_node = graph.add("abuffer", (
                    f"time_base={frame.time_base}:sample_rate={frame.sample_rate}:"
                    f"sample_fmt={frame.format.name}:channel_layout={frame.layout.name}"
                ))
                highpass = graph.add("highpass", "f=70" if preset == NATURAL_PRESET else "f=80")
                denoise = graph.add(
                    "afftdn",
                    (
                        "nr=14:nf=-48:tn=1" if preset == DISTANT_PRESET
                        else "nr=4:nf=-55:tn=1" if preset == NATURAL_PRESET
                        else "nr=8:nf=-50:tn=1"
                    ),
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
                elif preset == NATURAL_PRESET:
                    # Fairlight-inspired natural dialogue chain: preserve the room and
                    # transients, soften the harsh upper-mid band and avoid automatic
                    # limiter gain.  This is intended for already intelligible sources
                    # where LEVEL_V2 can expose metallic/raspy denoise artefacts.
                    presence = graph.add("equalizer", "f=3800:t=q:w=1.1:g=-1.5")
                    booster = graph.add("volume", "volume=1.5dB")
                    leveler = None
                    compressor = graph.add(
                        "acompressor",
                        "threshold=0.18:ratio=1.6:attack=25:release=220:makeup=1.05",
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
                    else "limit=0.891:attack=8:release=80:level=false"
                    if preset == NATURAL_PRESET
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
                    if presence is not None:
                        denoise.link_to(presence)
                        presence.link_to(compressor)
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
            if processed % 250 == 0 and progress_duration > 0:
                position = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
                state["progress_percent"] = min(99, int(position / progress_duration * 100))
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

    source_clock = clock.finish()
    duration = source_clock.duration_seconds
    check = av.open(str(output))
    check_stream = next(stream for stream in check.streams if stream.type == "audio")
    output_duration = float(check_stream.duration * check_stream.time_base) if check_stream.duration else None
    check.close()
    if output_duration is None or not duration:
        raise RuntimeError("Durata sorgente/output audio non disponibile")
    sync_delta = output_duration - duration
    if abs(sync_delta) > (1 / 30):
        raise RuntimeError(f"Audio non sincronizzato: differenza {sync_delta:.3f}s")
    silence_windows = detect_silence_windows(output)
    serialized_silences = [{"start": start, "end": end} for start, end in silence_windows]
    state.update(status="COMPLETED", progress_percent=100, output_path=str(output),
                 source_duration_seconds=duration, output_duration_seconds=output_duration,
                 sync_delta_seconds=sync_delta, output_sha256=file_sha256(output),
                  sample_rate=48000, channels=2, silence_windows=serialized_silences,
                  silence_windows_sha256=silence_windows_sha256(serialized_silences))
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

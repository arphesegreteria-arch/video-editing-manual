from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
import random
import struct
from typing import Any
import wave
from fractions import Fraction

import av
import numpy as np

from .artifact_records import ProducerId, artifact_store_for
from .artifact_hygiene import validate_managed_path
from .diagnostic_tools import capture_timeline_frames
from .resolve_connection import safe_call
from .safety import ValidationError, require_arphe_name
from .timeline_tools import duplicate_timeline, find_timeline


def _write_reference_slap_wav(path: Path, reference_path: Path,
                              duration_seconds: float, sample_rate: int) -> dict[str, object]:
    frame_count = int(round(duration_seconds * sample_rate))
    chunks: list[np.ndarray] = []
    with av.open(str(reference_path)) as container:
        stream = next((item for item in container.streams if item.type == "audio"), None)
        if stream is None:
            raise ValueError("Il riferimento SBAM non contiene audio")
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=sample_rate)
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                samples = converted.to_ndarray()
                if samples.ndim != 2 or samples.shape[0] != 2:
                    raise ValueError("Layout audio SBAM non supportato")
                chunks.append(samples.T.astype(np.float64, copy=False))
        for converted in resampler.resample(None):
            samples = converted.to_ndarray()
            chunks.append(samples.T.astype(np.float64, copy=False))
    if not chunks:
        raise ValueError("Il riferimento SBAM e' vuoto")
    source = np.concatenate(chunks, axis=0)
    peak_source = int(np.argmax(np.max(np.abs(source), axis=1)))
    desired_peak = int(round(0.018 * sample_rate))
    start = max(0, peak_source - desired_peak)
    selected = source[start:start + frame_count]
    if len(selected) < frame_count:
        selected = np.pad(selected, ((0, frame_count - len(selected)), (0, 0)))
    peak_value = float(np.max(np.abs(selected)))
    if peak_value <= 0.0:
        raise ValueError("Il riferimento SBAM non contiene un transiente")
    selected *= 0.985 / peak_value
    fade_in = min(frame_count, int(round(0.002 * sample_rate)))
    fade_out = min(frame_count, int(round(0.025 * sample_rate)))
    selected[:fade_in] *= np.linspace(0.0, 1.0, fade_in, endpoint=True)[:, None]
    selected[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, endpoint=True)[:, None]
    pcm = np.clip(np.rint(selected * 32767.0), -32767, 32767).astype("<i2")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return {"path": str(path), "duration_seconds": frame_count / sample_rate,
            "sample_rate": sample_rate, "frame_count": frame_count,
            "peak": int(np.max(np.abs(pcm))), "source": "reference_slap"}


def write_sbam_wav(path: Path, duration_seconds: float = 0.5,
                   sample_rate: int = 48000,
                   reference_path: Path | None = None) -> dict[str, object]:
    """Write a deterministic STCHAFF: friction, crack, then a short air tail."""
    if duration_seconds <= 0 or sample_rate <= 0:
        raise ValueError("Durata e sample rate SBAM devono essere positivi")
    if reference_path is not None:
        return _write_reference_slap_wav(
            Path(path), Path(reference_path), duration_seconds, sample_rate)
    frame_count = int(round(duration_seconds * sample_rate))
    rng = random.Random(9321)
    previous_noise = 0.0
    peak = 0
    frames = bytearray()
    for index in range(frame_count):
        t = index / sample_rate
        noise = rng.uniform(-1.0, 1.0)
        high_pass = noise - 0.88 * previous_noise
        previous_noise = noise
        crack_at = 0.018
        approach = min(1.0, t / crack_at)
        friction = 0.34 * high_pass * approach * approach if t < crack_at else 0.0
        after = max(0.0, t - crack_at)
        if t >= crack_at:
            crack = 0.72 * high_pass * math.exp(-105.0 * after)
            snap = (
                math.sin(2.0 * math.pi * 1850.0 * after)
                + 0.62 * math.sin(2.0 * math.pi * 3650.0 * after + 0.4)
                + 0.28 * math.sin(2.0 * math.pi * 6100.0 * after + 1.0)
            ) * math.exp(-125.0 * after)
            air_tail = 0.25 * high_pass * math.exp(-18.0 * after)
            body = 0.18 * math.sin(2.0 * math.pi * 108.0 * after) * math.exp(-15.0 * after)
        else:
            crack = snap = air_tail = body = 0.0
        raw = friction + crack + 0.31 * snap + air_tail + body
        value = math.tanh(raw * 1.9) / math.tanh(1.9)
        fade_in = min(1.0, index / max(1, int(0.0005 * sample_rate)))
        fade_out = min(1.0, (frame_count - index - 1) / max(1, int(0.035 * sample_rate)))
        sample = int(round(max(-0.985, min(0.985, value * fade_in * fade_out)) * 32767))
        peak = max(peak, abs(sample))
        frames.extend(struct.pack("<hh", sample, sample))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))
    return {"path": str(path), "duration_seconds": frame_count / sample_rate,
            "sample_rate": sample_rate, "frame_count": frame_count, "peak": peak}


def write_freeze_video(still_path: Path, output_path: Path,
                       duration_frames: int = 15, fps: int = 30) -> dict[str, object]:
    if duration_frames <= 0 or fps <= 0:
        raise ValueError("Durata e fps freeze devono essere positivi")
    with av.open(str(still_path)) as source_container:
        source_frame = next(source_container.decode(video=0))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(output_path), "w") as output_container:
        stream = output_container.add_stream("libx264", rate=fps)
        stream.width = source_frame.width
        stream.height = source_frame.height
        stream.pix_fmt = "yuv420p"
        frame = source_frame.reformat(format="yuv420p")
        for index in range(duration_frames):
            frame.pts = index
            frame.time_base = Fraction(1, fps)
            for packet in stream.encode(frame):
                output_container.mux(packet)
        for packet in stream.encode():
            output_container.mux(packet)
    return {"path": str(output_path), "duration_frames": duration_frames, "fps": fps}


def require_vertical_freeze_canvas(width: int, height: int) -> tuple[int, int]:
    """A freeze must be captured after the 9:16 canvas is established."""
    if width != 1080 or height != 1920:
        raise ValidationError("Il freeze SBAM richiede una timeline verticale 1080x1920")
    return width, height


def build_freeze_plan(timeline_start: int, timeline_end: int,
                      video_tail_start: int, video_tail_source_start: int,
                      audio_source_start: int, insert_frame: int,
                      duration_frames: int) -> dict[str, dict[str, int]]:
    if not timeline_start < insert_frame == video_tail_start < timeline_end:
        raise ValueError("Punto freeze non coerente con la coda video")
    if duration_frames <= 0:
        raise ValueError("Durata freeze non valida")
    tail_duration = timeline_end - insert_frame
    shifted_start = insert_frame + duration_frames
    shifted_end = timeline_end + duration_frames
    audio_split = audio_source_start + (insert_frame - timeline_start)
    audio_end = audio_source_start + (timeline_end - timeline_start)
    return {
        "freeze": {"record_start": insert_frame, "record_end": shifted_start},
        "video_tail": {"source_start": video_tail_source_start,
                       "source_end": video_tail_source_start + tail_duration,
                       "record_start": shifted_start, "record_end": shifted_end},
        "audio_prefix": {"source_start": audio_source_start, "source_end": audio_split,
                         "record_start": timeline_start, "record_end": insert_frame},
        "audio_tail": {"source_start": audio_split, "source_end": audio_end,
                       "record_start": shifted_start, "record_end": shifted_end},
        "sbam": {"record_start": insert_frame, "record_end": shifted_start},
    }


def _media_id(media: Any) -> str:
    return str(safe_call(media, "GetMediaId") or "")


def _folder_items(folder: Any):
    for item in safe_call(folder, "GetClipList") or []:
        yield item
    for child in safe_call(folder, "GetSubFolderList") or []:
        yield from _folder_items(child)


def _import_or_find(pool: Any, path: Path) -> Any:
    wanted = str(path.resolve()).casefold()
    root = safe_call(pool, "GetRootFolder")
    existing = [item for item in _folder_items(root)
                if str(Path(str(safe_call(item, "GetClipProperty", "File Path") or "")).resolve()).casefold()
                == wanted]
    if len(existing) == 1:
        return existing[0]
    imported = safe_call(pool, "ImportMedia", [str(path)]) or []
    if len(imported) == 1:
        return imported[0]
    root = safe_call(pool, "GetRootFolder")
    matches = [item for item in _folder_items(root)
               if str(Path(str(safe_call(item, "GetClipProperty", "File Path") or "")).resolve()).casefold()
               == wanted]
    if len(matches) != 1:
        raise RuntimeError(f"Import media freeze SBAM fallito: {path.suffix}")
    return matches[0]


def _matching_items(timeline: Any, kind: str, track: int, media: Any,
                    record_start: int, record_end: int) -> list[Any]:
    expected_media = _media_id(media)
    return [item for item in (safe_call(timeline, "GetItemListInTrack", kind, track) or [])
            if _media_id(safe_call(item, "GetMediaPoolItem")) == expected_media
            and safe_call(item, "GetStart") == record_start
            and safe_call(item, "GetEnd") == record_end]


def _append_segment(pool: Any, timeline: Any, media: Any, kind: str, track: int,
                    source_start: int, source_end: int,
                    record_start: int, record_end: int) -> Any:
    if source_end <= source_start or record_end <= record_start:
        raise ValidationError("Segmento freeze senza durata")
    media_type = 1 if kind == "video" else 2
    end_frame = source_end
    safe_call(pool, "AppendToTimeline", [{
        "mediaPoolItem": media, "startFrame": source_start, "endFrame": end_frame,
        "recordFrame": record_start, "mediaType": media_type, "trackIndex": track,
    }])
    matches = _matching_items(timeline, kind, track, media, record_start, record_end)
    if len(matches) != 1:
        observed = [{"start": safe_call(item, "GetStart"), "end": safe_call(item, "GetEnd")}
                    for item in (safe_call(timeline, "GetItemListInTrack", kind, track) or [])]
        raise RuntimeError(f"Inserimento {kind} non verificato: "
                           f"expected={record_start}-{record_end}, observed={observed}")
    return matches[0]


def _one_covering(timeline: Any, kind: str, track: int,
                  start: int, end: int) -> Any:
    items = [item for item in (safe_call(timeline, "GetItemListInTrack", kind, track) or [])
             if int(safe_call(item, "GetStart") or -1) <= start
             and int(safe_call(item, "GetEnd") or -1) >= end]
    if len(items) != 1:
        raise ValidationError(f"Serve una sola clip {kind} per il freeze")
    return items[0]


def _require_new_outputs(store: Any, outputs: tuple[Path, ...]) -> None:
    """Called under the local guard; never reuse even a missing registered file."""
    registered = {Path(record.path) for record in store.records()}
    for path in outputs:
        if path.exists() or path.is_symlink() or path in registered:
            raise ValidationError("Output freeze already exists or is registered; choose a new target name")


def _publish_new_file(private_path: Path, destination: Path) -> None:
    """Publish complete bytes atomically without replacing any destination.

    Both names are on the same volume. Hard-link creation fails atomically if
    destination already exists, including on Windows; no replace fallback is safe.
    """
    with private_path.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.link(private_path, destination)
    private_path.unlink()


def apply_freeze_sbam(resolve: Any, project: Any, config: Any, registry: Any,
                      source_timeline: str, target_name: str,
                      freeze_source_offset: int = 160,
                      insert_frame: int = 108180,
                      duration_frames: int = 15) -> dict[str, object]:
    source = find_timeline(project, source_timeline)
    if source is None:
        raise ValidationError("Timeline sorgente freeze non trovata")
    if safe_call(project, "SetCurrentTimeline", source) is not True:
        raise RuntimeError("Selezione timeline sorgente freeze fallita")
    timeline_start = int(safe_call(source, "GetStartFrame"))
    timeline_end = int(safe_call(source, "GetEndFrame"))
    fps = int(round(float(safe_call(source, "GetSetting", "timelineFrameRate") or 0)))
    canvas_width = int(float(safe_call(source, "GetSetting", "timelineResolutionWidth") or 0))
    canvas_height = int(float(safe_call(source, "GetSetting", "timelineResolutionHeight") or 0))
    require_vertical_freeze_canvas(canvas_width, canvas_height)
    if fps != 30 or duration_frames != 15:
        raise ValidationError("Il freeze SBAM richiede 30 fps e 15 frame")
    freeze_absolute = timeline_start + freeze_source_offset
    if not timeline_start <= freeze_absolute < insert_frame < timeline_end:
        raise ValidationError("Frame sorgente freeze o punto di inserimento non valido")

    store = artifact_store_for(config)
    require_arphe_name(target_name, "timeline")
    wav_path = validate_managed_path(
        Path(config.audio_root) / f"{target_name}_SBAM.wav", Path(config.audio_root))
    freeze_video_path = validate_managed_path(
        Path(config.render_root) / "staging" / f"{target_name}_FREEZE_{duration_frames}F.mp4",
        Path(config.render_root))
    outputs = (wav_path, freeze_video_path)
    with store.registration_guard():
        _require_new_outputs(store, outputs)
    project_id = store.bind_project(safe_call(project, "GetUniqueId"))

    private_paths: list[Path] = []
    try:
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix=f".{output.stem}.", suffix=output.suffix, dir=output.parent)
            os.close(descriptor)
            private_paths.append(Path(name))
        reference_slap = Path(config.asset_root) / "sfx" / "pixabay-hard-slap-46388.wav"
        audio_evidence = write_sbam_wav(
            private_paths[0],
            reference_path=reference_slap if reference_slap.is_file() else None,
        )
        capture_result = capture_timeline_frames(resolve, project, source, config, registry,
                                                 [freeze_source_offset])
        still_path = getattr(capture_result[-1], "path", None)
        if not isinstance(still_path, Path) or not still_path.is_file():
            raise RuntimeError("Cattura still freeze fallita")
        write_freeze_video(still_path, private_paths[1], duration_frames, fps)

        # Revalidate the complete pair after generation, then serialize
        # publication and registration with every cooperating producer.
        with store.registration_guard():
            validate_managed_path(wav_path, Path(config.audio_root))
            validate_managed_path(freeze_video_path, Path(config.render_root))
            _require_new_outputs(store, outputs)
            for private_path, destination in zip(private_paths, outputs, strict=True):
                _publish_new_file(private_path, destination)
            try:
                for path, root_id in ((wav_path, "audio_root"), (freeze_video_path, "render_root")):
                    store.register_produced_path(path, project_id=project_id,
                        category="RESOLVE_REFERENCE", protection_class="PROTECTED",
                        producer=ProducerId.APPLY_FREEZE_SBAM, managed_root_id=root_id,
                        hold_reasons=("RESOLVE_IMPORTED",))
            except Exception as exc:
                raise RuntimeError(f"Artifact registration failed; freeze/SBAM outputs retained for review: {exc}") from exc
    finally:
        # Only these unique, private generation names are disposable here.
        # Published destinations and all existing records remain untouched.
        for private_path in private_paths:
            private_path.unlink(missing_ok=True)
    pool = safe_call(project, "GetMediaPool")
    if pool is None:
        raise RuntimeError("Media pool non disponibile")
    still_media = _import_or_find(pool, freeze_video_path)
    sbam_media = _import_or_find(pool, wav_path)

    existing_target = find_timeline(project, target_name)
    if existing_target is not None:
        failed_v1 = safe_call(existing_target, "GetItemListInTrack", "video", 1) or []
        failed_a1 = safe_call(existing_target, "GetItemListInTrack", "audio", 1) or []
        if len(failed_v1) not in (3, 4) or len(failed_a1) > 1:
            raise ValidationError("Timeline destinazione gia' esistente e non riconoscibile come tentativo fallito")
        if safe_call(pool, "DeleteTimelines", [existing_target]) is not True:
            raise RuntimeError("Pulizia timeline freeze fallita non riuscita")

    duplicated = duplicate_timeline(project, config, registry, source_timeline, None, target_name)
    if not duplicated.get("ok"):
        return {**duplicated, "action": "apply_freeze_sbam"}
    timeline = safe_call(project, "GetCurrentTimeline")
    video_tail = _one_covering(timeline, "video", 1, insert_frame, timeline_end)
    if safe_call(video_tail, "GetStart") != insert_frame or safe_call(video_tail, "GetEnd") != timeline_end:
        raise ValidationError("La coda video deve iniziare esattamente alla fine del B/N")
    audio_original = _one_covering(timeline, "audio", 1, timeline_start, timeline_end)
    if safe_call(audio_original, "GetStart") != timeline_start or safe_call(audio_original, "GetEnd") != timeline_end:
        raise ValidationError("A1 deve essere una clip continua prima del freeze")
    video_media = safe_call(video_tail, "GetMediaPoolItem")
    audio_media = safe_call(audio_original, "GetMediaPoolItem")
    if video_media is None or audio_media is None:
        raise ValidationError("Media originali freeze non disponibili")
    video_source_start = int(safe_call(video_tail, "GetSourceStartFrame") or 0)
    audio_source_start = int(safe_call(audio_original, "GetSourceStartFrame") or 0)
    plan = build_freeze_plan(timeline_start, timeline_end, insert_frame, video_source_start,
                             audio_source_start, insert_frame, duration_frames)
    audio_track_added = False
    if int(safe_call(timeline, "GetTrackCount", "audio") or 0) < 2:
        if safe_call(timeline, "AddTrack", "audio", "stereo") is not True:
            raise RuntimeError("Creazione traccia A2 SBAM fallita")
        audio_track_added = True

    inserted: list[Any] = []
    try:
        if safe_call(timeline, "DeleteClips", [video_tail, audio_original], False) is not True:
            raise RuntimeError("Rimozione elementi originali dalla copia fallita")
        freeze = plan["freeze"]
        inserted.append(_append_segment(pool, timeline, still_media, "video", 1, 0,
                                        duration_frames, freeze["record_start"], freeze["record_end"]))
        tail = plan["video_tail"]
        inserted.append(_append_segment(pool, timeline, video_media, "video", 1,
                                        tail["source_start"], tail["source_end"],
                                        tail["record_start"], tail["record_end"]))
        prefix = plan["audio_prefix"]
        inserted.append(_append_segment(pool, timeline, audio_media, "audio", 1,
                                        prefix["source_start"], prefix["source_end"],
                                        prefix["record_start"], prefix["record_end"]))
        audio_tail = plan["audio_tail"]
        inserted.append(_append_segment(pool, timeline, audio_media, "audio", 1,
                                        audio_tail["source_start"], audio_tail["source_end"],
                                        audio_tail["record_start"], audio_tail["record_end"]))
        sbam = plan["sbam"]
        inserted.append(_append_segment(pool, timeline, sbam_media, "audio", 2, 0,
                                        duration_frames, sbam["record_start"], sbam["record_end"]))
    except Exception:
        if inserted:
            safe_call(timeline, "DeleteClips", inserted, False)
        _append_segment(pool, timeline, video_media, "video", 1, video_source_start,
                        video_source_start + (timeline_end - insert_frame),
                        insert_frame, timeline_end)
        _append_segment(pool, timeline, audio_media, "audio", 1, audio_source_start,
                        audio_source_start + (timeline_end - timeline_start),
                        timeline_start, timeline_end)
        if audio_track_added and not (safe_call(timeline, "GetItemListInTrack", "audio", 2) or []):
            safe_call(timeline, "DeleteTrack", "audio", 2)
        raise

    return {
        "ok": True, "action": "apply_freeze_sbam",
        "created_timeline": str(safe_call(timeline, "GetName") or ""),
        "freeze_source_offset": freeze_source_offset,
        "insert_frame": insert_frame, "duration_frames": duration_frames,
        "freeze_range": [insert_frame, insert_frame + duration_frames],
        "timeline_end": timeline_end + duration_frames,
        "video_ranges": [[safe_call(item, "GetStart"), safe_call(item, "GetEnd")]
                         for item in (safe_call(timeline, "GetItemListInTrack", "video", 1) or [])],
        "audio_a1_ranges": [[safe_call(item, "GetStart"), safe_call(item, "GetEnd")]
                            for item in (safe_call(timeline, "GetItemListInTrack", "audio", 1) or [])],
        "audio_a2_ranges": [[safe_call(item, "GetStart"), safe_call(item, "GetEnd")]
                            for item in (safe_call(timeline, "GetItemListInTrack", "audio", 2) or [])],
        "sbam_audio": {"duration_seconds": audio_evidence["duration_seconds"],
                       "sample_rate": audio_evidence["sample_rate"],
                       "source": audio_evidence.get("source", "synthetic")},
        "source_preserved": True,
    }




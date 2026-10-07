from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import os
from pathlib import Path
import shutil
from typing import Any

import av

from .config import CreativeConfig
from .registry import Registry
from .render_batches import RenderBatch, transition_batch
from .resolve_connection import safe_call
from .safety import ValidationError


@dataclass(frozen=True)
class MediaProbe:
    container: str
    video_codec: str
    width: int
    height: int
    frame_rate: Fraction
    duration_seconds: Fraction
    audio_codec: str | None
    audio_sample_rate: int | None


@dataclass(frozen=True)
class RenderExpectation:
    container: str
    video_codec: str
    width: int
    height: int
    frame_rate: Fraction
    duration_seconds: Fraction
    audio_required: bool
    audio_codec: str | None
    audio_sample_rate: int | None


def _container(name: str) -> str:
    return "mp4" if "mp4" in name.split(",") else ("mov" if "mov" in name.split(",") else name.split(",")[0])


def probe_media(path: Path) -> MediaProbe:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValidationError("File render assente o vuoto")
    with av.open(str(path)) as container:
        video = next((stream for stream in container.streams if stream.type == "video"), None)
        audio = next((stream for stream in container.streams if stream.type == "audio"), None)
        if video is None:
            raise ValidationError("Stream video assente")
        rate = Fraction(video.average_rate) if video.average_rate else Fraction(0)
        if container.duration is not None:
            duration = Fraction(container.duration, av.time_base)
        elif video.duration is not None:
            duration = Fraction(video.duration) * Fraction(video.time_base)
        else:
            raise ValidationError("Durata media non disponibile")
        return MediaProbe(_container(container.format.name), video.codec_context.name,
                          video.codec_context.width, video.codec_context.height, rate, duration,
                          None if audio is None else audio.codec_context.name,
                          None if audio is None else audio.codec_context.sample_rate)


def verify_media(probe: MediaProbe, expected: RenderExpectation) -> list[str]:
    issues = []
    if probe.container.casefold() != expected.container.casefold(): issues.append("container mismatch")
    if probe.video_codec.casefold() != expected.video_codec.casefold(): issues.append("video_codec mismatch")
    if (probe.width, probe.height) != (expected.width, expected.height): issues.append("resolution mismatch")
    if probe.frame_rate != expected.frame_rate: issues.append("frame_rate mismatch")
    if abs(probe.duration_seconds - expected.duration_seconds) > Fraction(1, 1) / expected.frame_rate:
        issues.append("duration mismatch")
    if expected.audio_required and probe.audio_codec is None: issues.append("audio missing")
    if expected.audio_codec and probe.audio_codec and probe.audio_codec.casefold() != expected.audio_codec.casefold():
        issues.append("audio_codec mismatch")
    if expected.audio_sample_rate and probe.audio_sample_rate != expected.audio_sample_rate:
        issues.append("audio_sample_rate mismatch")
    return issues


def expectation_from_batch(batch: RenderBatch) -> RenderExpectation:
    duration = (batch.evidence or {}).get("expected_duration_seconds")
    if duration is None:
        raise ValidationError("Durata attesa non registrata nel batch")
    return RenderExpectation(batch.container, batch.video_codec.casefold(), batch.width, batch.height,
                             Fraction(batch.frame_rate), Fraction(str(duration)), batch.audio_required,
                             None if batch.audio_codec is None else batch.audio_codec.casefold(),
                             batch.audio_sample_rate)


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): value.update(chunk)
    return value.hexdigest()


def verify_and_promote_batch(project: Any, config: CreativeConfig, registry: Registry,
                             batch_id: str) -> dict[str, Any]:
    batch = registry.render_batch(batch_id)
    if batch is None or batch.status not in {"RENDERING", "VERIFYING"}:
        raise ValidationError("Batch non verificabile")
    if batch.status == "RENDERING":
        batch = transition_batch(registry, batch_id, "RENDERING", "VERIFYING", {})
    try:
        jobs = {str(job.get("JobId") or job.get("JobID")): str(job.get("JobStatus", ""))
                for job in (safe_call(project, "GetRenderJobList") or []) if isinstance(job, dict)}
        if any(jobs.get(job_id, "").casefold() not in {"complete", "completed"}
               for job_id in batch.created_job_ids):
            raise ValidationError("Uno o più job Resolve non risultano completati")
        expectation = expectation_from_batch(batch)
        staging = Path(batch.staging_directory or "")
        sources = [staging / name for name in batch.expected_outputs]
        problems = {source.name: verify_media(probe_media(source), expectation) for source in sources}
        problems = {name: issues for name, issues in problems.items() if issues}
        if problems:
            raise ValidationError(f"Output non conforme: {problems}")
        destination = (config.render_root / batch.delivery_class).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        targets = [destination / source.name for source in sources]
        if any(target.exists() for target in targets):
            raise ValidationError("Collisione nella destinazione finale")
        for source, target in zip(sources, targets, strict=True):
            try:
                os.replace(source, target)
            except OSError:
                shutil.copy2(source, target)
                if _digest(source) != _digest(target):
                    target.unlink(missing_ok=True)
                    raise ValidationError("Hash della copia finale non conforme")
                source.unlink()
        verified = transition_batch(registry, batch_id, "VERIFYING", "VERIFIED",
                                    {"verified_outputs": [target.name for target in targets]})
        registry.release_render_lock(batch.project_name, batch.batch_id)
        return {"ok": True, "action": "verify_render_batch", "batch_id": batch_id,
                "status": verified.status, "outputs": [target.name for target in targets]}
    except Exception as exc:
        transition_batch(registry, batch_id, "VERIFYING", "FAILED_VERIFY", {"verify_error": str(exc)})
        registry.release_render_lock(batch.project_name, batch.batch_id)
        raise

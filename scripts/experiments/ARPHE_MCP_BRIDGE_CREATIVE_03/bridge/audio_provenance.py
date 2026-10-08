from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .config import CreativeConfig
from .safety import ValidationError


JOB_ID = re.compile(r"^audio_[0-9a-f]{16}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_COMPLETE_FIELDS = {
    "schema", "job_id", "status", "preset", "source_fingerprint", "output_path",
    "output_sha256", "source_duration_seconds", "output_duration_seconds",
    "sync_delta_seconds", "sample_rate", "channels",
}


@dataclass(frozen=True)
class VerifiedAudio:
    path: Path
    audio_job_id: str
    preset: str
    source_fingerprint: str
    output_sha256: str
    output_duration_seconds: float
    sync_delta_seconds: float


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValidationError(f"File provenance non leggibile: {exc}") from exc
    return digest.hexdigest()


def media_fingerprint(path: Path) -> str:
    if not path.is_file():
        raise ValidationError("Media sorgente non trovato")
    return file_sha256(path)


def _finite_number(value: object, name: str, *, allow_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} deve essere numerico")
    result = float(value)
    if result != result or abs(result) == float("inf") or (not allow_negative and result < 0):
        raise ValidationError(f"{name} fuori intervallo")
    return result


def verify_audio_manifest(config: CreativeConfig, audio_job_id: str,
                          expected_source_fingerprint: str) -> VerifiedAudio:
    if not isinstance(audio_job_id, str) or not JOB_ID.fullmatch(audio_job_id):
        raise ValidationError("audio_job_id non valido")
    if not isinstance(expected_source_fingerprint, str) or not SHA256.fullmatch(expected_source_fingerprint):
        raise ValidationError("Fingerprint sorgente atteso non valido")
    manifest_path = config.audio_jobs_root / f"{audio_job_id}.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Manifest audio non leggibile: {exc}") from exc
    if not isinstance(manifest, dict) or REQUIRED_COMPLETE_FIELDS - set(manifest):
        raise ValidationError("Manifest audio V2 incompleto")
    if manifest.get("schema") != "ARPHE_AUDIO_JOB_V2" or manifest.get("status") != "COMPLETED":
        raise ValidationError("Serve un manifest audio V2 COMPLETED")
    if manifest.get("job_id") != audio_job_id:
        raise ValidationError("Manifest audio associato a un job differente")
    if manifest.get("source_fingerprint") != expected_source_fingerprint:
        raise ValidationError("Audio derivato da una sorgente differente")
    from .audio_tools import allowed_audio
    try:
        output = allowed_audio(str(manifest.get("output_path", "")), config)
    except OSError as exc:
        raise ValidationError(f"WAV del manifest non disponibile: {exc}") from exc
    recorded_hash = manifest.get("output_sha256")
    if not isinstance(recorded_hash, str) or not SHA256.fullmatch(recorded_hash):
        raise ValidationError("Hash WAV nel manifest non valido")
    if file_sha256(output) != recorded_hash:
        raise ValidationError("Il WAV corrente non corrisponde al manifest")
    source_duration = _finite_number(manifest.get("source_duration_seconds"), "source_duration_seconds")
    output_duration = _finite_number(manifest.get("output_duration_seconds"), "output_duration_seconds")
    sync_delta = _finite_number(manifest.get("sync_delta_seconds"), "sync_delta_seconds",
                                allow_negative=True)
    if source_duration <= 0 or output_duration <= 0:
        raise ValidationError("Durata audio non valida")
    if abs((output_duration - source_duration) - sync_delta) > 0.001:
        raise ValidationError("Metadati di sincronizzazione incoerenti")
    if abs(sync_delta) > (1 / 30):
        raise ValidationError("Audio fuori sincronizzazione oltre 1/30 di secondo")
    if manifest.get("sample_rate") != 48000 or manifest.get("channels") != 2:
        raise ValidationError("Formato WAV editoriale non supportato")
    preset = manifest.get("preset")
    if not isinstance(preset, str) or not preset:
        raise ValidationError("Preset audio mancante")
    return VerifiedAudio(
        path=output,
        audio_job_id=audio_job_id,
        preset=preset,
        source_fingerprint=expected_source_fingerprint,
        output_sha256=recorded_hash,
        output_duration_seconds=output_duration,
        sync_delta_seconds=sync_delta,
    )

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from typing import Any

from .audio_worker import DISTANT_PRESET, LEVEL_PRESET, PRESET, PRESETS
from .config import CreativeConfig
from .longform_tools import allowed_media
from .safety import ValidationError, arphe_name


JOB_ID = re.compile(r"^audio_[0-9a-f]{16}$")


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    return hashlib.sha256(f"{path}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()


def start_audio_job(config: CreativeConfig, media_path: str, preset: str = PRESET) -> dict[str, Any]:
    if not config.flags.get("CAP_LONGFORM"):
        raise RuntimeError("CAP_LONGFORM non configurata")
    source = allowed_media(media_path, config)
    if preset not in PRESETS:
        raise ValidationError("Preset audio non consentito")
    config.audio_root.mkdir(parents=True, exist_ok=True)
    config.audio_jobs_root.mkdir(parents=True, exist_ok=True)
    job_id = "audio_" + uuid.uuid4().hex[:16]
    source_name = arphe_name(source.stem, "LONGFORM").removeprefix("ARPHE_")
    label = "DISTANT" if preset == DISTANT_PRESET else ("LEVEL" if preset == LEVEL_PRESET else "CLEAN")
    output = config.audio_root / f"ARPHE_{label}_{source_name}_{job_id[-8:]}.wav"
    job_path = config.audio_jobs_root / f"{job_id}.json"
    payload = {"schema": "ARPHE_AUDIO_JOB_V1", "job_id": job_id, "status": "QUEUED",
               "progress_percent": 0, "preset": preset, "source_name": source.name,
               "source_fingerprint": _fingerprint(source), "output_path": str(output)}
    job_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    subprocess.Popen([sys.executable, "-m", "bridge.audio_worker", "--source", str(source),
                      "--output", str(output), "--job", str(job_path), "--preset", preset],
                     cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return {"ok": True, "action": "start_prepare_longform_audio", "job_id": job_id,
            "status": "QUEUED", "preset": preset, "writes_to_resolve": False}


def audio_job(config: CreativeConfig, job_id: str) -> dict[str, Any]:
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValidationError("job_id audio non valido")
    path = config.audio_jobs_root / f"{job_id}.json"
    if not path.is_file():
        raise ValidationError("Job audio non trovato")
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    result["ok"] = result.get("status") != "FAILED"
    result["action"] = "get_longform_audio_job"
    return result


def allowed_audio(path_value: str, config: CreativeConfig) -> Path:
    selected = Path(path_value).expanduser().resolve(strict=True)
    root = config.audio_root.resolve(strict=True)
    if selected.suffix.lower() != ".wav" or not selected.is_file() or not selected.is_relative_to(root):
        raise ValidationError("Audio restaurato fuori dalla cartella allowlisted")
    return selected

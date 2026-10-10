from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .safety import ValidationError


@dataclass(frozen=True)
class CameraSource:
    label: str
    path: str
    fps: float
    guide_audio: bool


@dataclass(frozen=True)
class LongformSourcePackage:
    mode: str
    program_path: str
    fps: float
    cameras: tuple[CameraSource, ...]

    @property
    def final_audio_source(self) -> str:
        return self.program_path


def inspect_longform_sources(raw: dict[str, Any]) -> LongformSourcePackage:
    mode = str(raw.get("mode", ""))
    if mode == "SINGLE":
        source = raw.get("source", {})
        return LongformSourcePackage(mode, str(source["path"]), float(source["fps"]), ())
    if mode != "OBS_MULTICAM":
        raise ValidationError("Modalità sorgente non supportata")
    program = raw.get("program")
    if not isinstance(program, dict) or not program.get("path"):
        raise ValidationError("Pacchetto OBS: PROGRAM obbligatorio")
    fps = float(program.get("fps", 0))
    cameras: list[CameraSource] = []
    labels: set[str] = set()
    for raw_camera in raw.get("cameras", []):
        camera = CameraSource(str(raw_camera.get("label", "")), str(raw_camera.get("path", "")), float(raw_camera.get("fps", 0)), bool(raw_camera.get("guide_audio", False)))
        if not camera.label or not camera.path or camera.label in labels:
            raise ValidationError("Etichetta camera mancante o duplicata")
        if camera.fps != fps:
            raise ValidationError("frame rate camera non coerente")
        labels.add(camera.label)
        cameras.append(camera)
    return LongformSourcePackage(mode, str(program["path"]), fps, tuple(cameras))


def build_sync_plan(package: LongformSourcePackage) -> dict[str, object]:
    if package.mode == "SINGLE":
        return {"status": "NOT_APPLICABLE", "final_audio_source": package.final_audio_source}
    status = "READY_FOR_NATIVE_SYNC" if package.cameras and all(camera.guide_audio for camera in package.cameras) else "REVIEW_REQUIRED"
    return {"status": status, "final_audio_source": package.final_audio_source, "camera_labels": [camera.label for camera in package.cameras]}

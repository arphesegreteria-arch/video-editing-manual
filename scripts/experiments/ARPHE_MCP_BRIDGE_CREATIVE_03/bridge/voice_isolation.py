"""Typed, guarded Voice Isolation access for the active Resolve timeline.

This module deliberately addresses only Resolve's documented Voice Isolation API.
It does not invoke Dialogue Separator, Fairlight presets, or external audio processing.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from contextlib import contextmanager
import json
import os
from pathlib import Path
from threading import Lock
import uuid
from typing import Any, Callable

from .safety import ValidationError


@dataclass(frozen=True)
class VoiceIsolationState:
    is_enabled: bool
    amount: int

    def as_dict(self) -> dict[str, bool | int]:
        return {"isEnabled": self.is_enabled, "amount": self.amount}


@dataclass(frozen=True)
class VoiceIsolationTarget:
    project_name: str
    timeline_name: str
    timeline_id: str
    track_index: int
    track_name: str


@dataclass(frozen=True)
class VoiceIsolationCapture:
    target: VoiceIsolationTarget
    initial: VoiceIsolationState


@dataclass(frozen=True)
class VoiceIsolationResult:
    target: VoiceIsolationTarget
    current: VoiceIsolationState


class VoiceIsolationStore:
    """Small fail-closed persistent ledger with recoverable interrupted applies."""
    _lock = Lock()

    def __init__(self, path: Path, workstation_id: str):
        self.path, self.workstation_id = path, workstation_id

    @contextmanager
    def _locked(self):
        """Protect ledger read/modify/write across threads and processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with self._lock, lock_path.open("a+b") as handle:
            handle.seek(0)
            handle.write(b"\\0")
            handle.flush()
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists(): return {"schema": "ARPHE_VOICE_ISOLATION_V1", "jobs": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("schema") != "ARPHE_VOICE_ISOLATION_V1" or not isinstance(raw.get("jobs"), dict):
            raise ValidationError("Ledger Voice Isolation non valido")
        return raw

    def _write(self, raw: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def prepare(self, capture: VoiceIsolationCapture, amount: int) -> dict[str, Any]:
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 100:
            raise ValidationError("amount Voice Isolation deve essere un intero tra 0 e 100")
        with self._locked():
            raw = self._read()
            target = asdict(capture.target)
            if any(job["state"] in {"PREPARED", "APPLYING", "APPLIED"} and job["target"] == target for job in raw["jobs"].values()):
                raise ValidationError("Esiste gia un job Voice Isolation attivo sul target")
            job_id = "voice_" + uuid.uuid4().hex
            job = {"job_id": job_id, "workstation_id": self.workstation_id, "state": "PREPARED",
                   "target": target, "initial": capture.initial.as_dict(), "requested": {"isEnabled": True, "amount": amount}}
            raw["jobs"][job_id] = job; self._write(raw); return job

    def get(self, job_id: str) -> dict[str, Any]:
        with self._locked():
            job = self._read()["jobs"].get(job_id)
            if not job or job.get("workstation_id") != self.workstation_id: raise ValidationError("Job Voice Isolation non trovato")
            return job

    def transition(self, job_id: str, expected: str, state: str) -> dict[str, Any]:
        with self._locked():
            raw = self._read(); job = raw["jobs"].get(job_id)
            if not job or job.get("workstation_id") != self.workstation_id or job.get("state") != expected:
                raise ValidationError("Transizione job Voice Isolation non valida")
            job["state"] = state; raw["jobs"][job_id] = job; self._write(raw); return job

    def transition_any(self, job_id: str, expected: set[str], state: str) -> dict[str, Any]:
        with self._locked():
            raw = self._read(); job = raw["jobs"].get(job_id)
            if (not job or job.get("workstation_id") != self.workstation_id
                    or job.get("state") not in expected):
                raise ValidationError("Transizione job Voice Isolation non valida")
            job["state"] = state; raw["jobs"][job_id] = job; self._write(raw); return job

    def apply(self, job_id: str, operation: Callable[[dict[str, Any]], Any]) -> Any:
        """Hold the interprocess lock through transition, Resolve operation, and final state."""
        with self._locked():
            raw = self._read(); job = raw["jobs"].get(job_id)
            if (not job or job.get("workstation_id") != self.workstation_id
                    or job.get("state") != "PREPARED"):
                raise ValidationError("Transizione job Voice Isolation non valida")
            job["state"] = "APPLYING"; raw["jobs"][job_id] = job; self._write(raw)
            result = operation(job)
            job["state"] = "APPLIED"; raw["jobs"][job_id] = job; self._write(raw)
            return result

    def restore(self, job_id: str, operation: Callable[[dict[str, Any]], Any]) -> tuple[Any, bool]:
        """Serialize restore and retain a durable intent marker across a process interruption."""
        with self._locked():
            raw = self._read(); job = raw["jobs"].get(job_id)
            if not job or job.get("workstation_id") != self.workstation_id:
                raise ValidationError("Job Voice Isolation non trovato")
            if job.get("state") == "RESTORED":
                return None, True
            if job.get("state") not in {"APPLYING", "APPLIED", "RESTORING"}:
                raise ValidationError("Transizione job Voice Isolation non valida")
            if job["state"] != "RESTORING":
                job["state"] = "RESTORING"; raw["jobs"][job_id] = job; self._write(raw)
            result = operation(job)
            job["state"] = "RESTORED"; raw["jobs"][job_id] = job; self._write(raw)
            return result, False


def _method(obj: Any, name: str) -> Any:
    method = getattr(obj, name, None)
    if not callable(method):
        raise ValidationError(f"API Voice Isolation non disponibile: {name}")
    return method


def _state(raw: Any) -> VoiceIsolationState:
    if not isinstance(raw, dict) or set(raw) != {"isEnabled", "amount"}:
        raise ValidationError("Getter Voice Isolation ha restituito uno stato non tipizzato")
    enabled, amount = raw["isEnabled"], raw["amount"]
    if not isinstance(enabled, bool) or isinstance(amount, bool) or not isinstance(amount, int):
        raise ValidationError("Getter Voice Isolation ha restituito tipi non validi")
    if not 0 <= amount <= 100:
        raise ValidationError("Getter Voice Isolation ha restituito amount fuori intervallo")
    return VoiceIsolationState(enabled, amount)


def _target(project: Any, timeline: Any, track_index: int) -> VoiceIsolationTarget:
    if isinstance(track_index, bool) or not isinstance(track_index, int) or track_index < 1:
        raise ValidationError("track_index Voice Isolation non valido")
    project_name = _method(project, "GetName")()
    timeline_name = _method(timeline, "GetName")()
    timeline_id = _method(timeline, "GetUniqueId")()
    count = _method(timeline, "GetTrackCount")("audio")
    track_name = _method(timeline, "GetTrackName")("audio", track_index)
    if (not all(isinstance(value, str) and value for value in (project_name, timeline_name, timeline_id, track_name))
            or isinstance(count, bool) or not isinstance(count, int) or track_index > count):
        raise ValidationError("Target Voice Isolation non stabile o non disponibile")
    return VoiceIsolationTarget(project_name, timeline_name, timeline_id, track_index, track_name)


def capture_track(project: Any, timeline: Any, track_index: int) -> VoiceIsolationCapture:
    target = _target(project, timeline, track_index)
    initial = _state(_method(timeline, "GetVoiceIsolationState")(track_index))
    _method(timeline, "SetVoiceIsolationState")
    return VoiceIsolationCapture(target, initial)


def _validate_target(project: Any, timeline: Any, expected: VoiceIsolationTarget) -> None:
    actual = _target(project, timeline, expected.track_index)
    if actual != expected:
        raise ValidationError("Target Voice Isolation cambiato dopo la cattura")


def _set_and_readback(timeline: Any, target: VoiceIsolationTarget,
                      desired: VoiceIsolationState) -> VoiceIsolationResult:
    if _method(timeline, "SetVoiceIsolationState")(target.track_index, desired.as_dict()) is not True:
        raise RuntimeError("SetVoiceIsolationState fallita")
    current = _state(_method(timeline, "GetVoiceIsolationState")(target.track_index))
    if current != desired:
        raise RuntimeError("SetVoiceIsolationState read-back non corrispondente")
    return VoiceIsolationResult(target, current)


def apply_voice_isolation(project: Any, timeline: Any, capture: VoiceIsolationCapture,
                          amount: int) -> VoiceIsolationResult:
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 100:
        raise ValidationError("amount Voice Isolation deve essere un intero tra 0 e 100")
    _validate_target(project, timeline, capture.target)
    return _set_and_readback(timeline, capture.target, VoiceIsolationState(True, amount))


def restore_voice_isolation(project: Any, timeline: Any, capture: VoiceIsolationCapture,
                            expected_current: VoiceIsolationState) -> VoiceIsolationResult:
    _validate_target(project, timeline, capture.target)
    current = _state(_method(timeline, "GetVoiceIsolationState")(capture.target.track_index))
    if current != expected_current:
        raise ValidationError("Stato Voice Isolation cambiato da un job concorrente; ripristino bloccato")
    return _set_and_readback(timeline, capture.target, capture.initial)


def read_voice_isolation(project: Any, timeline: Any,
                         capture: VoiceIsolationCapture) -> VoiceIsolationResult:
    _validate_target(project, timeline, capture.target)
    return VoiceIsolationResult(capture.target,
                                _state(_method(timeline, "GetVoiceIsolationState")(capture.target.track_index)))

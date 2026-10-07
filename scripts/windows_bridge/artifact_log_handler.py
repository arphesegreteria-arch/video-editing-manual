"""Size-based log rotation that hands complete artifacts to bridge maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from logging.handlers import BaseRotatingHandler
import os
from pathlib import Path
import tempfile
from uuid import uuid4


ARTIFACT_SCHEMA_VERSION = 1
UTC = timezone.utc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ArtifactRotatingFileHandler(BaseRotatingHandler):
    """Rotate into immutable, uniquely named producer directories without deleting backups."""

    def __init__(self, filename: Path | str, workstation_id: str, max_bytes: int,
                 encoding: str = "utf-8") -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.workstation_id = workstation_id
        self.max_bytes = int(max_bytes)
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        super().__init__(str(path), mode="a", encoding=encoding, delay=False)

    def shouldRollover(self, record: logging.LogRecord) -> bool:  # noqa: N802
        if self.stream is None:
            self.stream = self._open()
        message = self.format(record) + self.terminator
        self.stream.seek(0, os.SEEK_END)
        return self.stream.tell() + len(message.encode(self.encoding or "utf-8")) >= self.max_bytes

    def doRollover(self) -> None:  # noqa: N802
        if self.stream:
            self.stream.close()
            self.stream = None
        active = Path(self.baseFilename)
        if not active.exists() or active.stat().st_size == 0:
            self.stream = self._open()
            return
        created = datetime.now(UTC)
        rotated_root = active.parent / "rotated"
        rotated_root.mkdir(parents=True, exist_ok=True)
        stamp = created.strftime("%Y%m%dT%H%M%S%fZ")
        producer = rotated_root / f"runtime.{stamp}.{uuid4().hex[:12]}"
        producer.mkdir()
        rotated_log = producer / "runtime.log"
        try:
            os.replace(active, rotated_log)
            _atomic_json(producer / "artifact.json", {
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "workstation_id": self.workstation_id,
                "category": "ROTATED_LOG",
                "log_file": "runtime.log",
                "created_at": created.isoformat(),
                "size_bytes": rotated_log.stat().st_size,
                "sha256": _sha256(rotated_log),
            })
        finally:
            self.stream = self._open()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.shouldRollover(record):
                self.doRollover()
            logging.FileHandler.emit(self, record)
        except Exception:
            self.handleError(record)

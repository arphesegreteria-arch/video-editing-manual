from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .safety import ValidationError


class Registry:
    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": 1, "projects": {}, "elements": {},
                    "briefs": {}, "render_batches": {}, "render_locks": {}}
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if data.get("schema_version") != 1:
            raise ValueError("Versione registry non supportata")
        data.setdefault("projects", {})
        data.setdefault("elements", {})
        data.setdefault("briefs", {})
        data.setdefault("render_batches", {})
        data.setdefault("render_locks", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def add_project(self, project: str) -> None:
        data = self._load()
        data["projects"].setdefault(project, {"timelines": []})
        self._save(data)

    def add_timeline(self, project: str, timeline: str) -> None:
        data = self._load()
        record = data["projects"].setdefault(project, {"timelines": []})
        if timeline not in record["timelines"]:
            record["timelines"].append(timeline)
        self._save(data)

    def project_allowed(self, project: str) -> bool:
        return project in self._load()["projects"]

    def timeline_allowed(self, project: str, timeline: str) -> bool:
        return timeline in self._load()["projects"].get(project, {}).get("timelines", [])

    def remove_timeline(self, project: str, timeline: str) -> None:
        data = self._load()
        record = data["projects"].get(project)
        if record and timeline in record.get("timelines", []):
            record["timelines"].remove(timeline)
        self._save(data)

    def remove_project(self, project: str) -> None:
        data = self._load()
        data["projects"].pop(project, None)
        self._save(data)

    def add_element(self, element_id: str, payload: dict[str, Any]) -> None:
        data = self._load()
        data["elements"][element_id] = payload
        self._save(data)

    def element(self, element_id: str) -> dict[str, Any] | None:
        return self._load()["elements"].get(element_id)

    def set_longform_batch(self, project: str, master_timeline: str,
                           clip_timelines: list[str]) -> None:
        data = self._load()
        record = data["projects"].setdefault(project, {"timelines": []})
        record["longform_batch"] = {"master_timeline": master_timeline,
                                    "clip_timelines": list(clip_timelines)}
        self._save(data)

    def longform_batch(self, project: str) -> dict[str, Any] | None:
        return self._load()["projects"].get(project, {}).get("longform_batch")

    def save_brief(self, brief: Any) -> None:
        from dataclasses import asdict
        data = self._load()
        payload = asdict(brief)
        for key in ("requested_outputs", "unresolved_questions"):
            payload[key] = list(payload[key])
        data["briefs"][brief.brief_id] = payload
        self._save(data)

    def brief(self, brief_id: str) -> dict[str, Any] | None:
        return self._load()["briefs"].get(brief_id)

    def save_render_batch(self, batch: Any) -> None:
        from dataclasses import asdict
        data = self._load()
        payload = asdict(batch)
        for key in ("timeline_names", "output_names", "queue_before", "created_job_ids", "expected_outputs"):
            payload[key] = list(payload[key])
        data["render_batches"][batch.batch_id] = payload
        self._save(data)

    def render_batch(self, batch_id: str) -> Any | None:
        from .render_batches import render_batch_from_dict
        raw = self._load()["render_batches"].get(batch_id)
        return None if raw is None else render_batch_from_dict(raw)

    def list_render_batches(self) -> list[Any]:
        from .render_batches import render_batch_from_dict
        return [render_batch_from_dict(raw) for raw in self._load()["render_batches"].values()]

    def acquire_render_lock(self, project: str, batch_id: str) -> None:
        data = self._load()
        existing = data["render_locks"].get(project)
        if existing and existing.get("batch_id") != batch_id:
            raise ValidationError("Progetto già bloccato da un altro render batch")
        data["render_locks"][project] = {"batch_id": batch_id}
        self._save(data)

    def render_lock(self, project: str) -> dict[str, Any] | None:
        return self._load()["render_locks"].get(project)

    def release_render_lock(self, project: str, batch_id: str) -> None:
        data = self._load()
        existing = data["render_locks"].get(project)
        if existing and existing.get("batch_id") == batch_id:
            data["render_locks"].pop(project, None)
            self._save(data)

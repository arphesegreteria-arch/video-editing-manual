from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


class Registry:
    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": 1, "projects": {}, "elements": {}}
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if data.get("schema_version") != 1:
            raise ValueError("Versione registry non supportata")
        data.setdefault("projects", {})
        data.setdefault("elements", {})
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

    def add_element(self, element_id: str, payload: dict[str, Any]) -> None:
        data = self._load()
        data["elements"][element_id] = payload
        self._save(data)

    def element(self, element_id: str) -> dict[str, Any] | None:
        return self._load()["elements"].get(element_id)

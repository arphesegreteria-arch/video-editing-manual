"""Read-only inventory, simulation and legacy migration planning."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .artifact_hygiene import validate_managed_path
from .artifact_records import ArtifactPolicy, ArtifactRecord, ArtifactStore, sha256_file
from .config import CreativeConfig


UTC = timezone.utc


def inventory_roots(config: CreativeConfig) -> tuple[dict[str, str], ...]:
    roots = [
        {"root_id": "render_root", "mode": "SCAN_DISPOSABLE"},
        {"root_id": "runtime_log_root", "mode": "SCAN_DISPOSABLE"},
        {"root_id": "audio_root", "mode": "SCAN_PROTECTED"},
        {"root_id": "audio_jobs_root", "mode": "SCAN_PROTECTED"},
        {"root_id": "profile_root", "mode": "REFERENCE_ONLY"},
        {"root_id": "asset_root", "mode": "REFERENCE_ONLY"},
        {"root_id": "resolve_archive_root", "mode": "REFERENCE_ONLY"},
        {"root_id": "backup_evidence", "mode": "REFERENCE_ONLY_UNCONFIGURED"},
    ]
    roots.extend({"root_id": f"media_root_{index}", "mode": "REFERENCE_ONLY"}
                 for index, _ in enumerate(config.media_roots))
    return tuple(roots)


def _root_paths(config: CreativeConfig) -> dict[str, Path]:
    return {
        "render_root": config.render_root.resolve(),
        "runtime_log_root": config.runtime_log_root.resolve(),
        "audio_root": config.audio_root.resolve(),
        "audio_jobs_root": config.audio_jobs_root.resolve(),
        "profile_root": config.artifact_registry_path.parent.resolve(),
    }


def _display(path: Path, root_id: str, root: Path) -> str:
    return f"{root_id}:{path.relative_to(root).as_posix()}"


def _iter_recursive_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return ()
    result: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories
                          if not (current_path / name).is_symlink()]
        result.extend(current_path / name for name in files)
        result.extend(current_path / name for name in directories
                      if (current_path / name).is_symlink())
    return tuple(result)


def scan_artifacts(config: CreativeConfig, store: ArtifactStore) -> dict[str, Any]:
    roots = _root_paths(config)
    records = store.records()
    known = {Path(record.path).resolve(strict=False) for record in records
             if record.state != "PURGED"}
    items: list[dict[str, Any]] = []
    for record in records:
        root = roots.get(record.managed_root_id)
        state = "PROTECTED" if record.protection_class == "PROTECTED" else record.state
        display = f"{record.managed_root_id}:invalid"
        if root is not None:
            try:
                selected = validate_managed_path(Path(record.path), root,
                                                 allow_directory=record.kind == "directory")
                display = _display(selected, record.managed_root_id, root)
                if record.kind == "file" and record.sha256 and sha256_file(selected) != record.sha256:
                    state = "BLOCKED_HASH_DRIFT"
            except (OSError, ValueError):
                state = "BLOCKED_PATH"
        items.append({"artifact_id": record.artifact_id, "category": record.category,
                      "state": state, "display_path": display,
                      "bytes": int(record.size_bytes or 0)})
    locations: list[tuple[str, Path, bool]] = [
        ("render_root", config.render_root / "diagnostics", False),
        ("render_root", config.render_root / "technical-preview", False),
        ("render_root", config.render_root / "staging", False),
        ("runtime_log_root", config.runtime_log_root / "rotated", False),
        ("audio_root", config.audio_root, True),
        ("audio_jobs_root", config.audio_jobs_root, True),
    ]
    for root_id, location, recursive in locations:
        root = roots[root_id]
        candidates = _iter_recursive_files(location) if recursive else (
            tuple(location.iterdir()) if location.is_dir() else ()
        )
        for path in candidates:
            if path.resolve(strict=False) in known:
                continue
            state = "UNCLASSIFIED_PROTECTED"
            try:
                selected = validate_managed_path(path, root, allow_directory=path.is_dir())
                display = _display(selected, root_id, root)
                size = selected.stat().st_size if selected.is_file() else 0
            except (OSError, ValueError):
                display = f"{root_id}:blocked"
                size = 0
                state = "BLOCKED_LINK"
            items.append({"artifact_id": None, "category": "UNCLASSIFIED",
                          "state": state, "display_path": display, "bytes": size})
    summary: dict[str, dict[str, int]] = {}
    for item in items:
        bucket = summary.setdefault(item["state"], {"count": 0, "bytes": 0})
        bucket["count"] += 1
        bucket["bytes"] += item["bytes"]
    return {"ok": True, "action": "scan_artifacts", "roots": inventory_roots(config),
            "summary": summary, "items": items, "writes": False}


def simulate_maintenance(config: CreativeConfig, store: ArtifactStore,
                         policy: ArtifactPolicy, now_utc: datetime,
                         *, active_job_ids: tuple[str, ...]) -> dict[str, Any]:
    now = now_utc.astimezone(UTC)
    roots = _root_paths(config)
    active = set(active_job_ids)
    items: list[dict[str, Any]] = []
    quarantine_candidates: list[str] = []
    quarantine_bytes = 0
    purge_blocked_bytes = 0
    for record in store.records():
        root = roots.get(record.managed_root_id)
        display = f"{record.managed_root_id}:invalid"
        state = "HELD_PROTECTED" if record.protection_class == "PROTECTED" else "ACTIVE"
        if root is None:
            state = "BLOCKED_PATH"
        else:
            try:
                selected = validate_managed_path(
                    Path(record.quarantine_path or record.path), root,
                    allow_directory=record.kind == "directory",
                )
                display = _display(selected, record.managed_root_id, root)
                if record.kind == "file" and record.sha256 and sha256_file(selected) != record.sha256:
                    state = "BLOCKED_HASH_DRIFT"
                elif record.protection_class == "PROTECTED":
                    state = "HELD_REVIEW" if record.review_state == "PENDING" else "HELD_PROTECTED"
                elif record.batch_id in active:
                    state = "HELD_ACTIVE_JOB"
                elif record.dependencies or record.hold_reasons:
                    state = "HELD_DEPENDENCY"
                elif record.state == "QUARANTINED":
                    if record.purge_after is not None and now >= record.purge_after:
                        state = "PURGE_DISABLED"
                        purge_blocked_bytes += int(record.size_bytes or 0)
                    else:
                        state = "QUARANTINED"
                elif record.batch_id and record.eligible_at is None:
                    state = "HELD_AWAITING_TERMINAL"
                else:
                    eligible_at = record.eligible_at
                    if eligible_at is None:
                        eligible_at = record.created_at + timedelta(
                            seconds=policy.rules[record.category].active_seconds
                        )
                    if now >= eligible_at:
                        state = "DRY_RUN_QUARANTINE"
                        quarantine_candidates.append(record.artifact_id)
                        quarantine_bytes += int(record.size_bytes or 0)
            except (OSError, ValueError):
                state = "BLOCKED_PATH"
        items.append({"artifact_id": record.artifact_id, "category": record.category,
                      "state": state, "display_path": display,
                      "bytes": int(record.size_bytes or 0)})
    return {
        "ok": True, "action": "simulate_artifact_maintenance", "writes": False,
        "purge_enabled": False, "items": items,
        "quarantine_candidates": quarantine_candidates, "purge_candidates": [],
        "potential_quarantine_bytes": quarantine_bytes,
        "purge_blocked_bytes": purge_blocked_bytes,
    }


def plan_legacy_migration(config: CreativeConfig) -> dict[str, Any]:
    """Validate known legacy evidence and return proposals without touching the registry."""
    proposals: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    proposed: set[tuple[str, str]] = set()

    def propose(category: str, path: Path, root_id: str, managed_root: Path) -> None:
        display = root_id + ":" + path.relative_to(managed_root).as_posix()
        key = (category, display)
        if key not in proposed:
            proposed.add(key)
            proposals.append({"category": category, "display_path": display})

    def verified_entry(value: object) -> Path:
        if not isinstance(value, dict):
            raise ValueError("entry")
        path = validate_managed_path(Path(str(value.get("path") or "")),
                                     config.audio_root.resolve())
        if sha256_file(path) != value.get("sha256"):
            raise ValueError("fingerprint")
        return path
    root = config.audio_jobs_root.resolve()
    for manifest in sorted(_iter_recursive_files(root), key=lambda value: str(value).casefold()):
        if manifest.suffix.lower() != ".json":
            continue
        try:
            selected = validate_managed_path(manifest, root)
            payload = json.loads(selected.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict) or payload.get("status") != "COMPLETED":
                continue
            schema = payload.get("schema")
            if schema == "ARPHE_LISTENING_VARIANT_V1":
                source = verified_entry(payload.get("source"))
                reference = verified_entry(payload.get("reference_v5"))
                output = verified_entry(payload.get("output"))
                propose("AUDIO_SOURCE", source, "audio_root", config.audio_root.resolve())
                propose("AUDIO_DERIVATIVE", reference, "audio_root", config.audio_root.resolve())
                propose("AUDIO_DERIVATIVE", output, "audio_root", config.audio_root.resolve())
                propose("AUDIO_MANIFEST", selected, "audio_jobs_root", root)
                continue
            if schema == "ARPHE_TIMELINE_DIALOGUE_CLEANUP_JOB_V1":
                source = validate_managed_path(Path(str(payload.get("source_path") or "")),
                                               config.audio_root.resolve())
                output = validate_managed_path(Path(str(payload.get("processed_path") or "")),
                                               config.audio_root.resolve())
                if (sha256_file(source) != payload.get("source_fingerprint")
                        or sha256_file(output) != payload.get("output_fingerprint")):
                    raise ValueError("fingerprint")
                propose("AUDIO_SOURCE", source, "audio_root", config.audio_root.resolve())
                propose("AUDIO_DERIVATIVE", output, "audio_root", config.audio_root.resolve())
                propose("AUDIO_MANIFEST", selected, "audio_jobs_root", root)
                continue
            if schema != "ARPHE_AUDIO_JOB_V2":
                errors.append({"display_path": "audio_jobs_root:" + selected.relative_to(root).as_posix(),
                               "error_code": "MANUAL_REVIEW_SCHEMA"})
                continue
            output = validate_managed_path(Path(str(payload.get("output_path") or "")),
                                           config.audio_root.resolve())
            if sha256_file(output) != payload.get("output_sha256"):
                raise ValueError("fingerprint")
            propose("AUDIO_DERIVATIVE", output, "audio_root", config.audio_root.resolve())
            propose("AUDIO_MANIFEST", selected, "audio_jobs_root", root)
        except (OSError, ValueError, json.JSONDecodeError):
            errors.append({"display_path": "audio_jobs_root:blocked",
                           "error_code": "MANUAL_REVIEW_FINGERPRINT_OR_PATH"})
    colorist = config.colorist_jobs_path
    if colorist.is_file():
        try:
            payload = json.loads(colorist.read_text(encoding="utf-8-sig"))
            if payload.get("schema") == "ARPHE_COLORIST_JOBS_V1":
                propose("COLORIST_STATE", colorist.resolve(), "profile_root",
                        config.artifact_registry_path.parent.resolve())
            else:
                errors.append({"display_path": "profile_root:colorist_jobs.json",
                               "error_code": "MANUAL_REVIEW_SCHEMA"})
        except (OSError, json.JSONDecodeError):
            errors.append({"display_path": "profile_root:colorist_jobs.json",
                           "error_code": "MANUAL_REVIEW_SCHEMA"})
    return {"ok": not errors, "action": "plan_legacy_migration", "writes": False,
            "proposals": proposals, "errors": errors}

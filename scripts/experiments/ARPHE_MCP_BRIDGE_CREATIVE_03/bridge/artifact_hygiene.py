from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import stat
from typing import Any

from .artifact_records import ArtifactPolicy, ArtifactRecord, ArtifactStore
from .config import CreativeConfig


UTC = timezone.utc
ACTIVE_BATCH_STATES = frozenset({"DRAFT", "CONFIRMED", "PREPARED", "APPROVED", "RENDERING", "VERIFYING"})
FAILED_BATCH_STATES = frozenset({"FAILED_RENDER", "FAILED_VERIFY"})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp inventario privo di timezone")
    return value.astimezone(UTC)


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def validate_managed_path(path: Path, root: Path, *, allow_directory: bool = False) -> Path:
    root_resolved = root.resolve(strict=False)
    selected = path if path.is_absolute() else root_resolved / path
    selected_absolute = selected.absolute()
    try:
        common = Path(os.path.commonpath((str(root_resolved), str(selected.resolve(strict=False)))))
    except ValueError as exc:
        raise ValueError("Percorso fuori dal managed root") from exc
    if common != root_resolved:
        raise ValueError("Percorso fuori dal managed root")
    try:
        relative = selected_absolute.relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError("Percorso fuori dal managed root") from exc
    current = root.absolute()
    for part in relative.parts:
        current /= part
        if current.exists() and (current.is_symlink() or _is_reparse(current)):
            raise ValueError("Percorso symlink o reparse non consentito")
    resolved = selected.resolve(strict=False)
    if resolved.exists():
        if allow_directory and not resolved.is_dir():
            raise ValueError("Artefatto directory atteso")
        if not allow_directory and not resolved.is_file():
            raise ValueError("Artefatto file atteso")
    return resolved


def _roots(config: CreativeConfig) -> dict[str, Path]:
    return {
        "render_root": config.render_root.resolve(),
        "profile_root": config.artifact_registry_path.parent.resolve(),
        "runtime_log_root": config.runtime_log_root.resolve(),
    }


def _display(path: Path, root_id: str, root: Path) -> str:
    return f"{root_id}:{path.relative_to(root).as_posix()}"


def _record_item(record: ArtifactRecord, config: CreativeConfig, project_registry: Any,
                 policy: ArtifactPolicy, now: datetime) -> dict[str, Any]:
    roots = _roots(config)
    root = roots.get(record.managed_root_id)
    item = {
        "artifact_id": record.artifact_id,
        "category": record.category,
        "state": record.state,
        "display_path": f"{record.managed_root_id}:invalid",
        "bytes": record.size_bytes or 0,
        "eligible_at": None if record.eligible_at is None else record.eligible_at.isoformat(),
        "purge_after": None if record.purge_after is None else record.purge_after.isoformat(),
    }
    if root is None:
        item["state"] = "ERROR"
        item["error_code"] = "UNKNOWN_MANAGED_ROOT"
        return item
    try:
        path = validate_managed_path(Path(record.path), root, allow_directory=record.kind == "directory")
        item["display_path"] = _display(path, record.managed_root_id, root)
    except ValueError:
        item["state"] = "ERROR"
        item["error_code"] = "PATH_OUTSIDE_MANAGED_ROOT"
        return item
    if record.state in {"QUARANTINED", "RESTORED", "PURGED", "ERROR"}:
        return item
    rule = policy.rules[record.category]
    if record.batch_id:
        batch = project_registry.render_batch(record.batch_id)
        if batch is None:
            item["state"] = "ERROR"
            item["error_code"] = "BATCH_NOT_FOUND"
            return item
        if batch.status in ACTIVE_BATCH_STATES:
            item["state"] = "PROTECTED"
            return item
        if batch.status not in set(rule.terminal_batch_states):
            if not (record.category == "FAILED_RENDER_STAGING" and batch.status in FAILED_BATCH_STATES):
                item["state"] = "AWAITING_TERMINAL_SNAPSHOT" if batch.status in FAILED_BATCH_STATES else "ERROR"
                return item
        if record.terminal_observed_at is None or record.eligible_at is None:
            item["state"] = "AWAITING_TERMINAL_SNAPSHOT"
            return item
        item["state"] = "ELIGIBLE" if now >= record.eligible_at else "ACTIVE"
        return item
    eligible_at = record.eligible_at or record.created_at + timedelta(seconds=rule.active_seconds)
    item["eligible_at"] = eligible_at.isoformat()
    item["state"] = "ELIGIBLE" if now >= eligible_at else "ACTIVE"
    return item


def _unclassified(config: CreativeConfig, known_paths: set[Path]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    locations = (
        ("render_root", config.render_root / "diagnostics"),
        ("render_root", config.render_root / "technical-preview"),
        ("render_root", config.render_root / "staging"),
    )
    render_root = config.render_root.resolve()
    for root_id, directory in locations:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            try:
                resolved = validate_managed_path(path, render_root, allow_directory=path.is_dir())
            except ValueError:
                continue
            if resolved in known_paths or any(known in resolved.parents for known in known_paths):
                continue
            try:
                size = resolved.stat().st_size if resolved.is_file() else 0
            except OSError:
                size = 0
            result.append({
                "artifact_id": None,
                "category": "UNCLASSIFIED",
                "state": "UNCLASSIFIED",
                "display_path": _display(resolved, root_id, render_root),
                "bytes": size,
                "eligible_at": None,
                "purge_after": None,
            })
    return result


def inspect_artifacts(config: CreativeConfig, artifact_store: ArtifactStore, project_registry: Any,
                      policy: ArtifactPolicy, now_utc: datetime) -> dict[str, Any]:
    now = _utc(now_utc)
    records = artifact_store.records()
    items = [_record_item(record, config, project_registry, policy, now) for record in records]
    known_paths = {Path(record.path).resolve(strict=False) for record in records if record.state != "PURGED"}
    items.extend(_unclassified(config, known_paths))
    summary: dict[str, dict[str, int]] = {}
    for item in items:
        bucket = summary.setdefault(item["state"], {"count": 0, "bytes": 0})
        bucket["count"] += 1
        bucket["bytes"] += int(item.get("bytes") or 0)
    return {
        "ok": True,
        "action": "inspect_artifact_hygiene",
        "workstation_id": config.workstation_id,
        "policy_version": policy.policy_version,
        "summary": summary,
        "items": items,
    }

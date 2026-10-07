from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from .artifact_records import ArtifactPolicy, ArtifactRecord, ArtifactStore, sha256_file
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
    selected_path = record.quarantine_path if record.state == "QUARANTINED" else record.path
    try:
        path = validate_managed_path(Path(selected_path or record.path), root,
                                     allow_directory=record.kind == "directory")
        item["display_path"] = _display(path, record.managed_root_id, root)
    except ValueError:
        item["state"] = "ERROR"
        item["error_code"] = "PATH_OUTSIDE_MANAGED_ROOT"
        return item
    if record.state in {"QUARANTINED", "PURGED", "ERROR"}:
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
    item["state"] = "ELIGIBLE" if now >= eligible_at else record.state
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


def _directory_signature(path: Path) -> tuple[int, str, tuple[str, ...]]:
    total = 0
    digest = hashlib.sha256()
    names: list[str] = []
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix().casefold()):
        if item.is_symlink() or _is_reparse(item):
            raise ValueError("Contenuto symlink o reparse non consentito")
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError("Contenuto staging non regolare")
        relative = item.relative_to(path).as_posix()
        size = item.stat().st_size
        file_digest = sha256_file(item)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        names.append(relative)
        total += size
    return total, digest.hexdigest(), tuple(names)


def _signature(path: Path, kind: str) -> tuple[int, str, tuple[str, ...]]:
    if kind == "file":
        return path.stat().st_size, sha256_file(path), (path.name,)
    return _directory_signature(path)


def _lock_path(store: ArtifactStore) -> Path:
    return store.path.with_suffix(store.path.suffix + ".maintenance.lock")


def _acquire_lock(store: ArtifactStore) -> int | None:
    path = _lock_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None


def _release_lock(store: ArtifactStore, descriptor: int) -> None:
    os.close(descriptor)
    _lock_path(store).unlink(missing_ok=True)


def _record_by_id(store: ArtifactStore, artifact_id: str) -> ArtifactRecord:
    for record in store.records():
        if record.artifact_id == artifact_id:
            return record
    raise KeyError(artifact_id)


def _mark_error(store: ArtifactStore, record: ArtifactRecord, code: str) -> None:
    store.replace(replace(record, state="ERROR", last_error=code))


def _reconcile_pending(store: ArtifactStore) -> None:
    operation = store.pending_operation()
    if operation is None:
        return
    record = _record_by_id(store, str(operation["artifact_id"]))
    source = Path(str(operation["source"]))
    destination = Path(str(operation["destination"]))
    action = operation.get("type")
    if action == "MOVE_TO_QUARANTINE" and not source.exists() and destination.exists():
        size, digest, _ = _signature(destination, record.kind)
        if size != record.size_bytes or digest != record.sha256:
            raise RuntimeError("Riconciliazione quarantena con contenuto modificato")
        store.replace(replace(
            record,
            state="QUARANTINED",
            original_path=str(source),
            quarantine_path=str(destination),
            quarantined_at=datetime.fromisoformat(str(operation["at"])),
            purge_after=datetime.fromisoformat(str(operation["purge_after"])),
            last_error=None,
        ))
        store.clear_pending_operation()
        return
    if action == "RESTORE" and source.exists() and not destination.exists():
        store.replace(replace(
            record,
            state="RESTORED",
            path=str(source),
            original_path=str(source),
            quarantine_path=None,
            quarantined_at=None,
            purge_after=None,
            eligible_at=datetime.fromisoformat(str(operation["eligible_at"])),
            last_error=None,
        ))
        store.clear_pending_operation()
        return
    if action == "PURGE" and not source.exists():
        store.replace(replace(record, state="PURGED", last_error=None))
        store.clear_pending_operation()
        return
    raise RuntimeError("Operazione artefatto pendente non riconciliabile")


def _freeze_terminal(record: ArtifactRecord, store: ArtifactStore, project_registry: Any,
                     policy: ArtifactPolicy, now: datetime) -> ArtifactRecord:
    batch = project_registry.render_batch(record.batch_id)
    if batch is None:
        _mark_error(store, record, "BATCH_NOT_FOUND")
        return _record_by_id(store, record.artifact_id)
    if batch.status in ACTIVE_BATCH_STATES:
        return record
    category = "FAILED_RENDER_STAGING" if batch.status in FAILED_BATCH_STATES else "RENDER_STAGING"
    rule = policy.rules[category]
    if batch.status not in set(rule.terminal_batch_states):
        _mark_error(store, record, "UNEXPECTED_BATCH_STATE")
        return _record_by_id(store, record.artifact_id)
    path = Path(record.path)
    try:
        size, digest, names = _signature(path, record.kind)
    except (OSError, ValueError):
        _mark_error(store, record, "STAGING_NOT_READABLE")
        return _record_by_id(store, record.artifact_id)
    expected = set(getattr(batch, "expected_outputs", ()) or ())
    unexpected = set(names) - expected
    if unexpected:
        _mark_error(store, record, "UNEXPECTED_STAGING_CONTENT")
        return _record_by_id(store, record.artifact_id)
    frozen = replace(
        record,
        category=category,
        terminal_observed_at=now,
        eligible_at=now + timedelta(seconds=rule.active_seconds),
        size_bytes=size,
        sha256=digest,
        policy_version=policy.policy_version,
    )
    store.replace(frozen)
    return frozen


def _quarantine(config: CreativeConfig, store: ArtifactStore, record: ArtifactRecord,
                policy: ArtifactPolicy, now: datetime) -> None:
    root = _roots(config)[record.managed_root_id]
    source = validate_managed_path(Path(record.path), root, allow_directory=record.kind == "directory")
    size, digest, _ = _signature(source, record.kind)
    if record.size_bytes != size or record.sha256 != digest:
        _mark_error(store, record, "CONTENT_CHANGED")
        return
    container = root / ".arphe-quarantine" / record.artifact_id
    destination = container / "payload"
    container.mkdir(parents=True, exist_ok=False)
    purge_after = now + timedelta(seconds=policy.quarantine_seconds)
    store.set_pending_operation({
        "type": "MOVE_TO_QUARANTINE",
        "artifact_id": record.artifact_id,
        "source": str(source),
        "destination": str(destination),
        "at": now.isoformat(),
        "purge_after": purge_after.isoformat(),
    })
    os.replace(source, destination)
    store.replace(replace(
        record,
        state="QUARANTINED",
        original_path=str(source),
        quarantine_path=str(destination),
        quarantined_at=now,
        purge_after=purge_after,
        last_error=None,
    ))
    store.clear_pending_operation()


def _purge(store: ArtifactStore, record: ArtifactRecord) -> None:
    path = Path(record.quarantine_path or "")
    size, digest, _ = _signature(path, record.kind)
    if record.size_bytes != size or record.sha256 != digest:
        _mark_error(store, record, "QUARANTINE_CONTENT_CHANGED")
        return
    store.set_pending_operation({
        "type": "PURGE",
        "artifact_id": record.artifact_id,
        "source": str(path),
        "destination": "",
    })
    if record.kind == "directory":
        shutil.rmtree(path)
    else:
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass
    store.replace(replace(record, state="PURGED", last_error=None))
    store.clear_pending_operation()


def run_maintenance(config: CreativeConfig, artifact_store: ArtifactStore, project_registry: Any,
                    policy: ArtifactPolicy, now_utc: datetime) -> dict[str, Any]:
    now = _utc(now_utc)
    descriptor = _acquire_lock(artifact_store)
    if descriptor is None:
        return {"ok": False, "action": "run_artifact_maintenance",
                "error_code": "MAINTENANCE_LOCKED", "quarantined": [], "purged": []}
    quarantined: list[str] = []
    purged: list[str] = []
    try:
        _reconcile_pending(artifact_store)
        for original in artifact_store.records():
            record = original
            if record.state == "ERROR" or record.state == "PURGED":
                continue
            if record.batch_id and record.terminal_observed_at is None:
                record = _freeze_terminal(record, artifact_store, project_registry, policy, now)
            if record.state in {"ACTIVE", "ELIGIBLE", "RESTORED"}:
                if record.batch_id:
                    batch = project_registry.render_batch(record.batch_id)
                    if batch is None or batch.status in ACTIVE_BATCH_STATES or record.eligible_at is None:
                        continue
                rule = policy.rules[record.category]
                eligible_at = record.eligible_at or record.created_at + timedelta(seconds=rule.active_seconds)
                if now >= eligible_at:
                    _quarantine(config, artifact_store, record, policy, now)
                    updated = _record_by_id(artifact_store, record.artifact_id)
                    if updated.state == "QUARANTINED":
                        quarantined.append(record.artifact_id)
            elif record.state == "QUARANTINED" and record.purge_after is not None and now >= record.purge_after:
                _purge(artifact_store, record)
                if _record_by_id(artifact_store, record.artifact_id).state == "PURGED":
                    purged.append(record.artifact_id)
        artifact_store.set_maintenance_state(last_attempt_at=now, last_result="ok")
        return {"ok": True, "action": "run_artifact_maintenance",
                "workstation_id": config.workstation_id,
                "policy_version": policy.policy_version,
                "quarantined": quarantined, "purged": purged}
    except Exception as exc:
        try:
            artifact_store.set_maintenance_state(last_attempt_at=now, last_result="error")
        except Exception:
            pass
        return {"ok": False, "action": "run_artifact_maintenance",
                "error_code": type(exc).__name__, "quarantined": quarantined, "purged": purged}
    finally:
        _release_lock(artifact_store, descriptor)


def restore_artifact(config: CreativeConfig, artifact_store: ArtifactStore, artifact_id: str,
                     policy: ArtifactPolicy, now_utc: datetime) -> dict[str, Any]:
    now = _utc(now_utc)
    descriptor = _acquire_lock(artifact_store)
    if descriptor is None:
        return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "MAINTENANCE_LOCKED"}
    try:
        _reconcile_pending(artifact_store)
        record = _record_by_id(artifact_store, artifact_id)
        if record.state != "QUARANTINED" or not record.quarantine_path or not record.original_path:
            return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "NOT_QUARANTINED"}
        source = Path(record.quarantine_path)
        destination = Path(record.original_path)
        if destination.exists():
            return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "RESTORE_COLLISION"}
        size, digest, _ = _signature(source, record.kind)
        if record.size_bytes != size or record.sha256 != digest:
            _mark_error(artifact_store, record, "QUARANTINE_CONTENT_CHANGED")
            return {"ok": False, "action": "restore_quarantined_artifact",
                    "error_code": "QUARANTINE_CONTENT_CHANGED"}
        destination.parent.mkdir(parents=True, exist_ok=True)
        eligible_at = now + timedelta(seconds=policy.rules[record.category].active_seconds)
        artifact_store.set_pending_operation({
            "type": "RESTORE",
            "artifact_id": record.artifact_id,
            "source": str(destination),
            "destination": str(source),
            "eligible_at": eligible_at.isoformat(),
        })
        os.replace(source, destination)
        restored = replace(
            record,
            state="RESTORED",
            path=str(destination),
            original_path=str(destination),
            quarantine_path=None,
            quarantined_at=None,
            purge_after=None,
            eligible_at=eligible_at,
            last_error=None,
        )
        artifact_store.replace(restored)
        artifact_store.clear_pending_operation()
        try:
            source.parent.rmdir()
        except OSError:
            pass
        return {"ok": True, "action": "restore_quarantined_artifact",
                "artifact_id": artifact_id, "state": "RESTORED"}
    finally:
        _release_lock(artifact_store, descriptor)

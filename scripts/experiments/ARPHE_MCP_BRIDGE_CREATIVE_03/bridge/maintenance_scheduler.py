"""Lazy, profile-scoped artifact maintenance scheduling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
import time
from typing import Callable

from .artifact_hygiene import run_maintenance
from .artifact_records import artifact_store_for, load_artifact_policy
from .audit import write_audit
from .config import CreativeConfig
from .registry import Registry


UTC = timezone.utc
RUN_INTERVAL = timedelta(hours=24)


def run_if_due(config: CreativeConfig, *, now_utc: datetime | None = None) -> dict[str, object]:
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    if not config.flags.get("CAP_ARTIFACT_MAINTENANCE", False):
        return {"ok": True, "action": "lazy_artifact_maintenance", "ran": False, "reason": "disabled"}
    store = artifact_store_for(config)
    last_attempt = store.maintenance_state().last_attempt_at
    if last_attempt is not None and now < last_attempt + RUN_INTERVAL:
        return {"ok": True, "action": "lazy_artifact_maintenance", "ran": False, "reason": "not_due"}
    result = run_maintenance(
        config,
        store,
        Registry(config.state_path),
        load_artifact_policy(config.artifact_policy_path),
        now,
    )
    return {**result, "ran": True}


def start_lazy_maintenance(config_loader: Callable[[], CreativeConfig],
                           delay_seconds: float = 5) -> threading.Thread | None:
    def worker() -> None:
        config: CreativeConfig | None = None
        try:
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            config = config_loader()
            result = run_if_due(config)
            write_audit(config.audit_log_path, "lazy_artifact_maintenance", result)
        except Exception as exc:
            if config is not None:
                try:
                    write_audit(config.audit_log_path, "lazy_artifact_maintenance", {
                        "ok": False,
                        "stage": "runtime",
                        "error_type": type(exc).__name__,
                    })
                except Exception:
                    pass

    try:
        thread = threading.Thread(target=worker, name="arphe-artifact-maintenance", daemon=True)
        thread.start()
        return thread
    except Exception:
        return None

"""Install the complete V1 action allowlist into a local profile registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.handler_registry import HandlerRegistry
from scripts.remote_agent.handlers.agent_status import GetStatusParameters, PingParameters, get_status, ping
from scripts.remote_agent.handlers.capability_audit import CapabilityAuditParameters, run_capability_audit
from scripts.remote_agent.handlers.media import (
    CopyToWorkspaceParameters,
    FindMediaParameters,
    HashMediaParameters,
    ImportMediaParameters,
    ListMediaParameters,
    copy_to_workspace,
    find_media,
    hash_media,
    import_media,
    list_media,
)
from scripts.remote_agent.handlers.render_probe import RenderProbeParameters, run_render_probe
from scripts.remote_agent.handlers.sync_code import ApprovedCodeSync, SyncParameters, sync_approved_code
from scripts.remote_agent.handlers.tracking_probe import TrackingProbeParameters, run_tracking_probe


def register_handlers(
    registry: HandlerRegistry,
    config: AgentConfig,
    file_broker: object,
    resolve_manager: object,
    *,
    agent_version: str,
    source_commit: str,
    capability_audit_runner: Callable[[dict[str, object]], dict[str, object]] | None = None,
    tracking_probe_runner: Callable[[dict[str, object]], dict[str, object]] | None = None,
    render_probe_runner: Callable[[dict[str, object]], dict[str, object]] | None = None,
    code_sync: ApprovedCodeSync | None = None,
) -> None:
    """Register fixed handlers; enablement remains solely in ``HandlerRegistry``."""
    registry.register("PING", PingParameters, lambda _p: ping(config, agent_version=agent_version, source_commit=source_commit), idempotent=True)
    registry.register("GET_STATUS", GetStatusParameters, lambda _p: get_status(config, resolve_manager), idempotent=True)
    registry.register("LIST_MEDIA", ListMediaParameters, lambda p: list_media(p, file_broker), idempotent=True)
    registry.register("FIND_MEDIA", FindMediaParameters, lambda p: find_media(p, file_broker), idempotent=True)
    registry.register("HASH_MEDIA", HashMediaParameters, lambda p: hash_media(p, file_broker), idempotent=True)
    registry.register("COPY_TO_WORKSPACE", CopyToWorkspaceParameters, lambda p: copy_to_workspace(p, file_broker))
    registry.register("IMPORT_MEDIA", ImportMediaParameters, lambda p: import_media(p, file_broker, resolve_manager))
    registry.register("RUN_CAPABILITY_AUDIT", CapabilityAuditParameters, lambda p: run_capability_audit(p, resolve_manager, capability_audit_runner))
    registry.register("RUN_TRACKING_PROBE", TrackingProbeParameters, lambda p: run_tracking_probe(p, resolve_manager, tracking_probe_runner))
    registry.register("RUN_RENDER_PROBE", RenderProbeParameters, lambda p: run_render_probe(p, resolve_manager, render_probe_runner))
    registry.register("SYNC_APPROVED_CODE", SyncParameters, lambda p: sync_approved_code(p, code_sync))

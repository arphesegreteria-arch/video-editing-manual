"""Guarded adapter for the separately supplied capability audit implementation."""

from __future__ import annotations

from typing import Callable, Literal

from scripts.remote_agent.models import StrictModel


class CapabilityAuditParameters(StrictModel):
    project_name: Literal["ARPHE_TEST"] = "ARPHE_TEST"


def run_capability_audit(
    parameters: CapabilityAuditParameters, resolve_manager: object, audit_runner: Callable[[dict[str, object]], dict[str, object]] | None
) -> dict[str, object]:
    getattr(resolve_manager, "require_test_project")()
    if audit_runner is None:
        raise RuntimeError("capability audit adapter is not installed")
    return dict(audit_runner(parameters.model_dump()))

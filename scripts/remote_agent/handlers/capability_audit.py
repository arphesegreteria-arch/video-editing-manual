"""Guarded adapter for the separately supplied capability audit implementation."""

from __future__ import annotations

from typing import Callable, Literal

from scripts.remote_agent.cancellation import CancellationToken, require_not_cancelled
from scripts.remote_agent.models import StrictModel


class CapabilityAuditParameters(StrictModel):
    project_name: Literal["ARPHE_TEST"] = "ARPHE_TEST"


def run_capability_audit(
    parameters: CapabilityAuditParameters,
    resolve_manager: object,
    audit_runner: Callable[[dict[str, object], CancellationToken], dict[str, object]] | None,
    token: CancellationToken,
) -> dict[str, object]:
    require_not_cancelled(token)
    getattr(resolve_manager, "require_test_project")()
    if audit_runner is None:
        raise RuntimeError("capability audit adapter is not installed")
    result = dict(audit_runner(parameters.model_dump(), token))
    require_not_cancelled(token)
    return result

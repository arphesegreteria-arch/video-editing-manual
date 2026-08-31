"""Guarded adapter for controlled tracking probes."""

from __future__ import annotations

from typing import Callable

from pydantic import Field

from scripts.remote_agent.cancellation import CancellationToken, require_not_cancelled
from scripts.remote_agent.handlers.media import FolderAlias, _relative_path
from scripts.remote_agent.models import StrictModel
from pydantic import field_validator


class TrackingProbeParameters(StrictModel):
    source_alias: FolderAlias
    relative_path: str = Field(min_length=1, max_length=1024)

    _validate_relative_path = field_validator("relative_path")(_relative_path)


def run_tracking_probe(
    parameters: TrackingProbeParameters,
    resolve_manager: object,
    probe_runner: Callable[[dict[str, object], CancellationToken], dict[str, object]] | None,
    token: CancellationToken,
) -> dict[str, object]:
    require_not_cancelled(token)
    getattr(resolve_manager, "require_test_project")()
    if probe_runner is None:
        raise RuntimeError("tracking probe adapter is not installed")
    result = dict(probe_runner(parameters.model_dump(), token))
    require_not_cancelled(token)
    return result

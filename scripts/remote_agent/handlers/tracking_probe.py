"""Guarded adapter for controlled tracking probes."""

from __future__ import annotations

from typing import Callable

from pydantic import Field

from scripts.remote_agent.handlers.media import FolderAlias, _relative_path
from scripts.remote_agent.models import StrictModel
from pydantic import field_validator


class TrackingProbeParameters(StrictModel):
    source_alias: FolderAlias
    relative_path: str = Field(min_length=1, max_length=1024)

    _validate_relative_path = field_validator("relative_path")(_relative_path)


def run_tracking_probe(
    parameters: TrackingProbeParameters, resolve_manager: object, probe_runner: Callable[[dict[str, object]], dict[str, object]] | None
) -> dict[str, object]:
    getattr(resolve_manager, "require_test_project")()
    if probe_runner is None:
        raise RuntimeError("tracking probe adapter is not installed")
    return dict(probe_runner(parameters.model_dump()))

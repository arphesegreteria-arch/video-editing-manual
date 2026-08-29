"""Guarded adapter for short disposable render probes."""

from __future__ import annotations

from typing import Callable

from pydantic import Field, field_validator

from scripts.remote_agent.handlers.media import _relative_path
from scripts.remote_agent.models import StrictModel


class RenderProbeParameters(StrictModel):
    output_relative_path: str = Field(min_length=1, max_length=1024)

    _validate_output_path = field_validator("output_relative_path")(_relative_path)


def run_render_probe(
    parameters: RenderProbeParameters, resolve_manager: object, probe_runner: Callable[[dict[str, object]], dict[str, object]] | None
) -> dict[str, object]:
    getattr(resolve_manager, "require_test_project")()
    if probe_runner is None:
        raise RuntimeError("render probe adapter is not installed")
    return dict(probe_runner(parameters.model_dump()))

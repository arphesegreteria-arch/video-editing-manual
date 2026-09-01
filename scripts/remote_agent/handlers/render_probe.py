"""Guarded adapter for short disposable render probes."""

from __future__ import annotations

from typing import Callable
from pathlib import PureWindowsPath

from pydantic import Field, field_validator

from scripts.remote_agent.cancellation import CancellationToken, require_not_cancelled
from scripts.remote_agent.handlers.media import _relative_path
from scripts.remote_agent.models import StrictModel


class RenderProbeParameters(StrictModel):
    output_relative_path: str = Field(min_length=1, max_length=1024)

    _validate_output_path = field_validator("output_relative_path")(_relative_path)

    @field_validator("output_relative_path")
    @classmethod
    def output_must_be_a_supported_video(cls, value: str) -> str:
        if PureWindowsPath(value).suffix.casefold() not in {".mov", ".mp4"}:
            raise ValueError("render probe output must be a .mov or .mp4 file")
        return value


def run_render_probe(
    parameters: RenderProbeParameters,
    resolve_manager: object,
    probe_runner: Callable[[dict[str, object], CancellationToken], dict[str, object]] | None,
    token: CancellationToken,
) -> dict[str, object]:
    require_not_cancelled(token)
    getattr(resolve_manager, "require_test_project")()
    if probe_runner is None:
        raise RuntimeError("render probe adapter is not installed")
    result = dict(probe_runner(parameters.model_dump(), token))
    require_not_cancelled(token)
    return result

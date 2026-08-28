"""Schema-versioned data contracts for the ARPHE Remote Agent."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_RESULT_OUTPUT_DEPTH = 4
MAX_RESULT_OUTPUT_ITEMS = 50
MAX_RESULT_OUTPUT_STRING_LENGTH = 4096
MAX_RESULT_PAYLOAD_BYTES = 64 * 1024
MAX_RESULT_PATH_LENGTH = 1024
RESULT_FOLDER_ALIASES = frozenset({"incoming", "test_media", "workspace", "exports"})
_SECRET_KEY_PATTERN = re.compile(
    r"(?:token|secret|password|authorization|credential|api[_-]?key)", re.IGNORECASE
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?:\b(?:token|secret|password|authorization|credential|api[_-]?key)\s*[:=]"
    r"|\bbearer\s+\S+"
    r"|\bgh[pousr]_[A-Za-z0-9_]+\b"
    r"|\bgithub_pat_[A-Za-z0-9_]+\b)",
    re.IGNORECASE,
)


class StrictModel(BaseModel):
    """Reject fields that have not been explicitly introduced to V1."""

    model_config = ConfigDict(extra="forbid")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    ABORTED = "ABORTED"


class AgentState(str, Enum):
    ONLINE = "ONLINE"
    PAUSED = "PAUSED"
    RUNNING = "RUNNING"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


def _has_secret_like_value(value: str) -> bool:
    return bool(_SECRET_VALUE_PATTERN.search(value))


def _validate_result_output(value: Any, depth: int = 0) -> None:
    if depth > MAX_RESULT_OUTPUT_DEPTH:
        raise ValueError("result output nesting is too deep")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("result output must contain finite JSON numbers")
        return
    if isinstance(value, str):
        if len(value) > MAX_RESULT_OUTPUT_STRING_LENGTH:
            raise ValueError("result output string is too long")
        if _has_secret_like_value(value):
            raise ValueError("result output contains a secret-like value")
        return
    if isinstance(value, dict):
        if len(value) > MAX_RESULT_OUTPUT_ITEMS:
            raise ValueError("result output object has too many items")
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ValueError("result output keys must be strings")
            if len(key) > 128:
                raise ValueError("result output key is too long")
            if _SECRET_KEY_PATTERN.search(key):
                raise ValueError("result output contains a secret-like key")
            _validate_result_output(nested_value, depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_RESULT_OUTPUT_ITEMS:
            raise ValueError("result output collection has too many items")
        for nested_value in value:
            _validate_result_output(nested_value, depth + 1)
        return
    raise ValueError("result output must contain JSON-compatible values")


def _validate_alias_relative_path(path: str) -> None:
    parts = path.split("/")
    if (
        len(path) > MAX_RESULT_PATH_LENGTH
        or "\\" in path
        or len(parts) < 2
        or parts[0] not in RESULT_FOLDER_ALIASES
        or any(part in {"", ".", ".."} for part in parts[1:])
        or any(":" in part for part in parts[1:])
    ):
        raise ValueError("output paths must be alias-relative")


class Job(StrictModel):
    schema_version: Literal[1] = 1
    job_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
    target_machine: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=128)
    created_at: datetime
    requested_by: str = Field(min_length=1, max_length=128)
    retryable: bool
    timeout_seconds: int = Field(ge=5, le=7200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    lease_expires_at: datetime | None = None
    attempt: int = Field(default=0, ge=0)

    @field_validator("created_at", "claimed_at", "lease_expires_at")
    @classmethod
    def timestamps_must_be_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("timestamp must be UTC")
        return value.astimezone(timezone.utc)

    def is_for_machine(self, machine_id: str) -> bool:
        return self.target_machine == machine_id

    def matches_machine(self, machine_id: str) -> bool:
        """Compatibility-friendly spelling for queue consumers."""
        return self.is_for_machine(machine_id)


class JobResult(StrictModel):
    schema_version: Literal[1] = 1
    job_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
    machine_id: str = Field(min_length=1, max_length=64)
    status: JobStatus
    started_at: datetime
    finished_at: datetime
    action: str = Field(min_length=1, max_length=128)
    duration_seconds: float | None = Field(default=None, ge=0)
    output: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=50)
    error_type: str | None = Field(default=None, max_length=256)
    error_message: str | None = Field(default=None, max_length=4096)
    output_paths: list[str] = Field(default_factory=list, max_length=50)
    agent_version: str = Field(min_length=1, max_length=128)
    source_commit: str = Field(min_length=1, max_length=128)

    @field_validator("started_at", "finished_at")
    @classmethod
    def result_timestamps_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("timestamp must be UTC")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def result_must_be_safe_to_upload(self) -> "JobResult":
        _validate_result_output(self.output)
        for warning in self.warnings:
            if len(warning) > 1024 or _has_secret_like_value(warning):
                raise ValueError("warnings must be bounded and secret-free")
        for message in (self.error_type, self.error_message):
            if message is not None and _has_secret_like_value(message):
                raise ValueError("error details must be secret-free")
        for output_path in self.output_paths:
            _validate_alias_relative_path(output_path)
        try:
            payload = json.dumps(
                self.model_dump(mode="json"),
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("result payload must be JSON-serializable") from exc
        if len(payload.encode("utf-8")) > MAX_RESULT_PAYLOAD_BYTES:
            raise ValueError("result payload exceeds the GitHub result size limit")
        return self


class MachineHeartbeat(StrictModel):
    schema_version: Literal[1] = 1
    machine_id: str = Field(min_length=1, max_length=64)
    state: AgentState
    last_heartbeat_at: datetime
    agent_version: str = Field(min_length=1, max_length=128)
    source_commit: str = Field(min_length=1, max_length=128)
    resolve_connected: bool
    resolve_version: str | None = None
    current_job_id: str | None = Field(
        default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$"
    )
    workspace_free_bytes: int | None = Field(default=None, ge=0)
    exports_free_bytes: int | None = Field(default=None, ge=0)

    @field_validator("last_heartbeat_at")
    @classmethod
    def heartbeat_timestamp_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("timestamp must be UTC")
        return value.astimezone(timezone.utc)

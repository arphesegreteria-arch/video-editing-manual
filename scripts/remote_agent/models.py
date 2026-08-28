"""Schema-versioned data contracts for the ARPHE Remote Agent."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    warnings: list[str] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    output_paths: list[str] = Field(default_factory=list)
    agent_version: str = Field(min_length=1, max_length=128)
    source_commit: str = Field(min_length=1, max_length=128)

    @field_validator("started_at", "finished_at")
    @classmethod
    def result_timestamps_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("timestamp must be UTC")
        return value.astimezone(timezone.utc)


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

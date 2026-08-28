from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from scripts.remote_agent.models import Job, JobResult, JobStatus


def valid_job_data() -> dict:
    return {
        "schema_version": 1,
        "job_id": "audit-home-001",
        "target_machine": "HOME_DEV",
        "action": "RUN_CAPABILITY_AUDIT",
        "created_at": "2026-08-28T00:00:00Z",
        "requested_by": "arphe",
        "retryable": False,
        "timeout_seconds": 900,
        "parameters": {"project_name": "ARPHE_TEST"},
    }


def test_job_parses_valid_v1_payload_with_utc_timestamp() -> None:
    """Catches a job parser that loses the required V1 job contract."""
    job = Job.model_validate(valid_job_data())

    assert job.job_id == "audit-home-001"
    assert job.created_at == datetime(2026, 8, 28, tzinfo=timezone.utc)
    assert job.schema_version == 1


def test_job_rejects_unknown_top_level_fields() -> None:
    """Catches accepting unversioned remote-job fields without review."""
    payload = valid_job_data() | {"remote_command": "not allowed"}

    with pytest.raises(ValidationError, match="remote_command"):
        Job.model_validate(payload)


@pytest.mark.parametrize("job_id", ["-bad", "has space", "a" * 81])
def test_job_rejects_invalid_job_ids(job_id: str) -> None:
    """Catches IDs unsafe for the stable job filename convention."""
    payload = valid_job_data() | {"job_id": job_id}

    with pytest.raises(ValidationError, match="job_id"):
        Job.model_validate(payload)


@pytest.mark.parametrize("timeout_seconds", [4, 7201])
def test_job_rejects_timeouts_outside_v1_bounds(timeout_seconds: int) -> None:
    """Catches jobs that could bypass the agent's bounded execution policy."""
    payload = valid_job_data() | {"timeout_seconds": timeout_seconds}

    with pytest.raises(ValidationError, match="timeout_seconds"):
        Job.model_validate(payload)


def test_job_machine_match_helper_only_accepts_its_target() -> None:
    """Catches execution of a job intended for another local machine."""
    job = Job.model_validate(valid_job_data())

    assert job.is_for_machine("HOME_DEV") is True
    assert job.is_for_machine("POLI_01") is False


def test_job_result_serializes_allowed_fields_without_secrets() -> None:
    """Catches result payloads that leak credentials into the repository."""
    result = JobResult(
        job_id="audit-home-001",
        machine_id="HOME_DEV",
        action="RUN_CAPABILITY_AUDIT",
        status=JobStatus.SUCCEEDED,
        started_at="2026-08-28T00:00:00Z",
        finished_at="2026-08-28T00:00:05Z",
        output={"resolve_version": "19.1"},
        agent_version="1.0.0",
        source_commit="abc123",
    )

    payload = result.model_dump(mode="json")

    assert payload["status"] == "SUCCEEDED"
    assert payload["schema_version"] == 1
    assert {"token", "secret", "password", "authorization"}.isdisjoint(payload)

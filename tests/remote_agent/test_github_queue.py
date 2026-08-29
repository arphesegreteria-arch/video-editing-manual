import base64
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.remote_agent.config import GitHubConfig
from scripts.remote_agent.github_queue import (
    ClaimConflict,
    GitHubQueue,
    InvalidJob,
    LeaseActive,
    NonRetryableJob,
    QueueError,
    REMOTE_LOG_MAX_BYTES,
)
from scripts.remote_agent.models import AgentState, Job, JobResult, JobStatus, MachineHeartbeat


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers, json=None, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.responses.pop(0)


def encode_job(job):
    return base64.b64encode(json.dumps(job).encode()).decode()


def job_payload(**overrides):
    data = {
        "schema_version": 1,
        "job_id": "queue-001",
        "target_machine": "HOME_DEV",
        "action": "PING",
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "requested_by": "arphe",
        "retryable": False,
        "timeout_seconds": 30,
        "parameters": {},
    }
    data.update(overrides)
    return data


def queue(responses):
    transport = FakeTransport(responses)
    client = GitHubQueue(
        GitHubConfig(owner="arphe", repository="jobs", branch="main"),
        "github_pat_super-secret",
        transport=transport,
        request_timeout_seconds=7,
    )
    return client, transport


def content_response(payload, sha="blob-sha"):
    return FakeResponse(payload={"encoding": "base64", "content": encode_job(payload), "sha": sha})


def test_list_pending_parses_matching_jobs_and_ignores_other_machines():
    client, transport = queue([
        FakeResponse(payload=[
            {"name": "queue-001.json", "path": "jobs/queue-001.json", "sha": "a", "type": "file"},
            {"name": "queue-002.json", "path": "jobs/queue-002.json", "sha": "b", "type": "file"},
        ]),
        content_response(job_payload(), "a"),
        content_response(job_payload(job_id="queue-002", target_machine="POLI_01"), "b"),
    ])

    pending = client.list_pending("HOME_DEV")

    assert [(item.job.job_id, item.sha) for item in pending] == [("queue-001", "a")]
    assert all(call["timeout"] == 7 for call in transport.calls)


@pytest.mark.parametrize("payload", [b"not-json", json.dumps({"schema_version": 1}).encode()])
def test_invalid_json_or_schema_is_rejected_before_any_claim(payload):
    encoded = base64.b64encode(payload).decode()
    client, transport = queue([
        FakeResponse(payload=[{"name": "bad.json", "path": "jobs/bad.json", "sha": "x", "type": "file"}]),
        FakeResponse(payload={"encoding": "base64", "content": encoded, "sha": "x"}),
    ])

    with pytest.raises(InvalidJob):
        client.list_pending("HOME_DEV")

    assert [call["method"] for call in transport.calls] == ["GET", "GET"]


def test_filename_must_match_job_id():
    client, _ = queue([
        FakeResponse(payload=[{"name": "different.json", "path": "jobs/different.json", "sha": "x", "type": "file"}]),
        content_response(job_payload(), "x"),
    ])
    with pytest.raises(InvalidJob, match="filename"):
        client.list_pending("HOME_DEV")


@pytest.mark.parametrize("status", [409, 422])
def test_claim_maps_github_sha_conflicts(status):
    client, _ = queue([FakeResponse(status_code=status, text="sha conflict")])
    with pytest.raises(ClaimConflict):
        client.claim(Job.model_validate(job_payload()), "old", now=NOW)


def test_claim_sets_lease_attempt_and_uses_fetched_sha():
    client, transport = queue([FakeResponse(payload={"content": {"sha": "new"}})])
    claimed = client.claim(Job.model_validate(job_payload()), "old", now=NOW, lease_seconds=120)
    sent = json.loads(base64.b64decode(transport.calls[0]["json"]["content"]))
    assert claimed.status is JobStatus.CLAIMED
    assert claimed.claimed_by == "HOME_DEV"
    assert claimed.claimed_at == NOW
    assert claimed.lease_expires_at == NOW + timedelta(seconds=120)
    assert claimed.attempt == 1
    assert transport.calls[0]["json"]["sha"] == "old"
    assert sent["status"] == "CLAIMED"


def stale_job(*, retryable=True):
    return Job.model_validate(job_payload(
        retryable=retryable,
        status="CLAIMED",
        claimed_by="HOME_DEV",
        claimed_at=(NOW - timedelta(minutes=10)).isoformat(),
        lease_expires_at=(NOW - timedelta(seconds=1)).isoformat(),
        attempt=1,
    ))


def test_stale_lease_requires_retryable_and_idempotent_handler():
    client, _ = queue([])
    with pytest.raises(NonRetryableJob):
        client.claim(stale_job(retryable=False), "old", now=NOW, idempotent=True)
    with pytest.raises(NonRetryableJob):
        client.claim(stale_job(), "old", now=NOW, idempotent=False)


def test_active_lease_is_not_reclaimed():
    active = stale_job().model_copy(update={"lease_expires_at": NOW + timedelta(seconds=10)})
    client, _ = queue([])
    with pytest.raises(LeaseActive):
        client.claim(active, "old", now=NOW, idempotent=True)


def test_stale_safe_job_can_be_reclaimed():
    client, _ = queue([FakeResponse(payload={})])
    claimed = client.claim(stale_job(), "old", now=NOW, idempotent=True)
    assert claimed.attempt == 2
    assert claimed.status is JobStatus.CLAIMED


def test_mark_running_updates_only_a_claimed_job_with_sha_cas():
    claimed = Job.model_validate(job_payload(
        status="CLAIMED", claimed_by="HOME_DEV", claimed_at=NOW.isoformat(),
        lease_expires_at=(NOW + timedelta(minutes=5)).isoformat(), attempt=1,
    ))
    client, transport = queue([FakeResponse(payload={})])
    running = client.mark_running(claimed, "claimed-sha")
    assert running.status is JobStatus.RUNNING
    assert transport.calls[0]["json"]["sha"] == "claimed-sha"
    sent = json.loads(base64.b64decode(transport.calls[0]["json"]["content"]))
    assert sent["status"] == "RUNNING"


def result():
    return JobResult(
        job_id="queue-001", machine_id="HOME_DEV", status="SUCCEEDED",
        started_at=NOW, finished_at=NOW, action="PING",
        output={"ok": True}, output_paths=["workspace/result.json"],
        agent_version="1.0", source_commit="abc123",
    )


def heartbeat():
    return MachineHeartbeat(
        machine_id="HOME_DEV", state=AgentState.ONLINE, last_heartbeat_at=NOW,
        agent_version="1.0", source_commit="abc123", resolve_connected=False,
    )


def test_result_log_and_heartbeat_writers_use_bounded_safe_payloads():
    client, transport = queue([FakeResponse(payload={}), FakeResponse(payload={}), FakeResponse(payload={})])
    client.write_result(result())
    client.write_log("queue-001", "x" * (REMOTE_LOG_MAX_BYTES + 500))
    client.write_heartbeat(heartbeat())

    assert [call["method"] for call in transport.calls] == ["PUT", "PUT", "PUT"]
    assert "/contents/results/queue-001.json" in transport.calls[0]["url"]
    assert "/contents/logs/queue-001.log" in transport.calls[1]["url"]
    assert "/contents/machines/HOME_DEV.json" in transport.calls[2]["url"]
    remote_log = base64.b64decode(transport.calls[1]["json"]["content"])
    assert len(remote_log) <= REMOTE_LOG_MAX_BYTES
    assert remote_log.endswith(b"[TRUNCATED]\n")


def test_http_errors_redact_token():
    client, _ = queue([FakeResponse(status_code=500, text="github_pat_super-secret exploded")])
    with pytest.raises(QueueError) as exc:
        client.list_pending("HOME_DEV")
    assert "github_pat_super-secret" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)

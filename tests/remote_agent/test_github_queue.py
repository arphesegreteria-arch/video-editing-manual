import base64
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.remote_agent.config import GitHubConfig
from scripts.remote_agent.github_queue import (
    ClaimConflict,
    GitHubQueue,
    HttpError,
    InvalidJob,
    LeaseActive,
    NonRetryableJob,
    QueuedJob,
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


def queue(responses, *, token="github_pat_super-secret"):
    transport = FakeTransport(responses)
    client = GitHubQueue(
        GitHubConfig(owner="arphe", repository="jobs", branch="main"),
        token,
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
def test_invalid_json_or_schema_is_skipped_before_any_claim(payload):
    encoded = base64.b64encode(payload).decode()
    client, transport = queue([
        FakeResponse(payload=[{"name": "bad.json", "path": "jobs/bad.json", "sha": "x", "type": "file"}]),
        FakeResponse(payload={"encoding": "base64", "content": encoded, "sha": "x"}),
    ])

    assert client.list_pending("HOME_DEV") == []

    assert [call["method"] for call in transport.calls] == ["GET", "GET"]


@pytest.mark.parametrize(
    ("omit_sha", "document_sha"),
    [(True, None), (False, None), (False, ""), (False, 17)],
)
def test_list_pending_skips_missing_or_invalid_fetched_document_sha(omit_sha, document_sha):
    """Catches listed jobs acquiring a coerced, unusable Contents blob SHA."""
    document = content_response(job_payload())
    if omit_sha:
        del document._payload["sha"]
    else:
        document._payload["sha"] = document_sha
    client, transport = queue([
        FakeResponse(payload=[{"name": "queue-001.json", "path": "jobs/queue-001.json", "sha": "listed-sha", "type": "file"}]),
        document,
    ])

    assert client.list_pending("HOME_DEV") == []

    assert [call["method"] for call in transport.calls] == ["GET", "GET"]


@pytest.mark.parametrize("entry", ["not-a-directory-entry", None, 42, {"type": "file"}])
def test_malformed_listing_entries_raise_sanitized_invalid_job(entry):
    """Catches malformed directory payloads escaping as AttributeError during sorting."""
    client, transport = queue([FakeResponse(payload=[entry])])

    with pytest.raises(InvalidJob, match="listing entry"):
        client.list_pending("HOME_DEV")

    assert [call["method"] for call in transport.calls] == ["GET"]


def test_filename_must_match_job_id():
    client, _ = queue([
        FakeResponse(payload=[{"name": "different.json", "path": "jobs/different.json", "sha": "x", "type": "file"}]),
        content_response(job_payload(), "x"),
    ])
    assert client.list_pending("HOME_DEV") == []


@pytest.mark.parametrize("status", [409, 422])
def test_claim_maps_github_sha_conflicts(status):
    client, _ = queue([FakeResponse(status_code=status, text="sha conflict")])
    with pytest.raises(ClaimConflict):
        client.claim(Job.model_validate(job_payload()), "old", now=NOW)


def test_claim_conflict_mapping_uses_http_status_not_error_text():
    """Catches an unrelated error body containing '(409)' being treated as a CAS conflict."""
    client, _ = queue([FakeResponse(status_code=500, text="upstream diagnostic mentions (409)")])

    with pytest.raises(HttpError) as exc:
        client.claim(Job.model_validate(job_payload()), "old", now=NOW)

    assert exc.value.status_code == 500


def test_claim_sets_lease_attempt_and_uses_fetched_sha():
    client, transport = queue([FakeResponse(payload={"content": {"sha": "new"}})])
    claimed = client.claim(Job.model_validate(job_payload()), "old", now=NOW, lease_seconds=120)
    sent = json.loads(base64.b64decode(transport.calls[0]["json"]["content"]))
    assert claimed.sha == "new"
    assert claimed.job.status is JobStatus.CLAIMED
    assert claimed.job.claimed_by == "HOME_DEV"
    assert claimed.job.claimed_at == NOW
    assert claimed.job.lease_expires_at == NOW + timedelta(seconds=120)
    assert claimed.job.attempt == 1
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
    client, _ = queue([FakeResponse(payload={"content": {"sha": "reclaimed-sha"}})])
    claimed = client.claim(stale_job(), "old", now=NOW, idempotent=True)
    assert claimed.job.attempt == 2
    assert claimed.job.status is JobStatus.CLAIMED


def test_mark_running_updates_only_a_claimed_job_with_sha_cas():
    claimed = Job.model_validate(job_payload(
        status="CLAIMED", claimed_by="HOME_DEV", claimed_at=NOW.isoformat(),
        lease_expires_at=(NOW + timedelta(minutes=5)).isoformat(), attempt=1,
    ))
    client, transport = queue([FakeResponse(payload={"content": {"sha": "running-sha"}})])
    running = client.mark_running(QueuedJob(job=claimed, sha="claimed-sha"), now=NOW)
    assert running.sha == "running-sha"
    assert running.job.status is JobStatus.RUNNING
    assert transport.calls[0]["json"]["sha"] == "claimed-sha"
    sent = json.loads(base64.b64decode(transport.calls[0]["json"]["content"]))
    assert sent["status"] == "RUNNING"


def test_list_claim_and_mark_running_chain_uses_each_fresh_contents_sha():
    """Catches a claim response SHA being discarded before the running CAS update."""
    client, transport = queue([
        FakeResponse(payload=[
            {"name": "queue-001.json", "path": "jobs/queue-001.json", "sha": "listed-sha", "type": "file"},
        ]),
        content_response(job_payload(), "listed-sha"),
        FakeResponse(payload={"content": {"sha": "claimed-sha"}}),
        FakeResponse(payload={"content": {"sha": "running-sha"}}),
    ])

    pending = client.list_pending("HOME_DEV")
    claimed = client.claim(pending[0].job, pending[0].sha, now=NOW)
    running = client.mark_running(claimed, now=NOW)

    assert running.job.status is JobStatus.RUNNING
    assert running.sha == "running-sha"
    assert transport.calls[2]["json"]["sha"] == "listed-sha"
    assert transport.calls[3]["json"]["sha"] == "claimed-sha"


def test_complete_terminal_cas_chain_uses_the_running_revision_for_terminal_persistence():
    """Catches terminal persistence overwriting the running transition with an earlier Contents revision."""
    client, transport = queue([
        FakeResponse(payload=[
            {"name": "queue-001.json", "path": "jobs/queue-001.json", "sha": "listed-sha", "type": "file"},
        ]),
        content_response(job_payload(), "listed-sha"),
        FakeResponse(payload={"content": {"sha": "claimed-sha"}}),
        FakeResponse(payload={"content": {"sha": "running-sha"}}),
        FakeResponse(payload={"content": {"sha": "terminal-sha"}}),
    ])

    pending = client.list_pending("HOME_DEV")
    claimed = client.claim(pending[0].job, pending[0].sha, now=NOW)
    running = client.mark_running(claimed, now=NOW)
    terminal = client.mark_terminal(running, JobStatus.SUCCEEDED)

    assert terminal.job.status is JobStatus.SUCCEEDED
    assert terminal.sha == "terminal-sha"
    assert [call["json"]["sha"] for call in transport.calls[2:]] == ["listed-sha", "claimed-sha", "running-sha"]


@pytest.mark.parametrize("response_sha", ["", None, 17])
def test_claim_rejects_a_missing_or_non_string_response_sha(response_sha):
    """Catches later CAS operations receiving a coerced or empty GitHub blob SHA."""
    client, _ = queue([FakeResponse(payload={"content": {"sha": response_sha}})])

    with pytest.raises(QueueError, match="response SHA"):
        client.claim(Job.model_validate(job_payload()), "listed-sha", now=NOW)


@pytest.mark.parametrize(
    "claimed_job",
    [
        Job.model_validate(job_payload(
            status="CLAIMED", claimed_by="HOME_DEV", claimed_at=NOW.isoformat(),
            lease_expires_at=(NOW - timedelta(seconds=1)).isoformat(), attempt=1,
        )),
        Job.model_validate(job_payload(
            status="CLAIMED", claimed_by="POLI_01", claimed_at=NOW.isoformat(),
            lease_expires_at=(NOW + timedelta(minutes=5)).isoformat(), attempt=1,
        )),
    ],
)
def test_mark_running_rejects_expired_or_foreign_claim_before_put(claimed_job):
    """Catches running transitions after the lease or current-machine ownership is lost."""
    client, transport = queue([])

    with pytest.raises(QueueError):
        client.mark_running(QueuedJob(job=claimed_job, sha="claimed-sha"), now=NOW)

    assert transport.calls == []


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
    client, transport = queue([
        FakeResponse(status_code=404, payload={}), FakeResponse(status_code=201, payload={}),
        FakeResponse(status_code=404, payload={}), FakeResponse(status_code=201, payload={}),
        FakeResponse(status_code=404, payload={}), FakeResponse(status_code=201, payload={}),
    ])
    client.write_result(result())
    client.write_log("queue-001", "x" * (REMOTE_LOG_MAX_BYTES + 500))
    client.write_heartbeat(heartbeat())

    assert [call["method"] for call in transport.calls] == ["GET", "PUT", "GET", "PUT", "GET", "PUT"]
    assert "/contents/results/queue-001.json" in transport.calls[1]["url"]
    assert "/contents/logs/queue-001.log" in transport.calls[3]["url"]
    assert "/contents/machines/HOME_DEV.json" in transport.calls[5]["url"]
    remote_log = base64.b64decode(transport.calls[3]["json"]["content"])
    assert len(remote_log) <= REMOTE_LOG_MAX_BYTES
    assert remote_log.endswith(b"[TRUNCATED]\n")


def test_write_log_redacts_configured_and_generic_credentials_before_truncation():
    """Catches queue-log uploads exposing credentials that appear before the byte cap."""
    configured_token = "github_pat_configured-secret"
    client, transport = queue([
        FakeResponse(status_code=404, payload={}), FakeResponse(status_code=201, payload={})
    ], token=configured_token)

    client.write_log(
        "queue-001",
        f"token={configured_token}\nAuthorization: Bearer ghp_GenericSecret\n"
        + "x" * REMOTE_LOG_MAX_BYTES,
    )

    remote_log = base64.b64decode(transport.calls[1]["json"]["content"]).decode()
    assert configured_token not in remote_log
    assert "ghp_GenericSecret" not in remote_log
    assert remote_log.count("[REDACTED]") == 2
    assert remote_log.endswith("[TRUNCATED]\n")


@pytest.mark.parametrize("job_id", ["", "../machines/HOME_DEV", "job/escape", r"job\escape", "a" * 81])
def test_write_log_rejects_job_ids_outside_the_exact_job_namespace(job_id):
    """Catches logs being written outside logs/<valid-job-id>.log."""
    client, transport = queue([])

    with pytest.raises(InvalidJob):
        client.write_log(job_id, "safe log text")

    assert transport.calls == []


def test_http_errors_redact_token():
    client, _ = queue([FakeResponse(status_code=500, text="github_pat_super-secret exploded")])
    with pytest.raises(QueueError) as exc:
        client.list_pending("HOME_DEV")
    assert "github_pat_super-secret" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)


def test_existing_result_log_and_heartbeat_are_upserted_with_blob_sha():
    """Repeated singleton writes must use the current Contents blob as a CAS."""
    client, transport = queue([
        FakeResponse(payload={"sha": "result-old"}),
        FakeResponse(payload={}),
        FakeResponse(status_code=404, payload={"message": "Not Found"}),
        FakeResponse(status_code=201, payload={}),
        FakeResponse(payload={"sha": "heartbeat-old"}),
        FakeResponse(payload={}),
    ])

    client.write_result(result())
    client.write_log("queue-001", "safe")
    client.write_heartbeat(heartbeat())

    assert [call["method"] for call in transport.calls] == ["GET", "PUT", "GET", "PUT", "GET", "PUT"]
    assert transport.calls[1]["json"]["sha"] == "result-old"
    assert "sha" not in transport.calls[3]["json"]
    assert transport.calls[5]["json"]["sha"] == "heartbeat-old"


def test_upsert_conflict_fails_safely_without_retrying_over_newer_content():
    client, transport = queue([
        FakeResponse(payload={"sha": "old"}),
        FakeResponse(status_code=409, text="conflict github_pat_super-secret"),
    ])

    with pytest.raises(ClaimConflict, match="changed"):
        client.write_heartbeat(heartbeat())

    assert len(transport.calls) == 2


def test_malformed_job_document_does_not_hide_a_later_valid_job():
    client, _ = queue([
        FakeResponse(payload=[
            {"name": "bad.json", "path": "jobs/bad.json", "sha": "bad", "type": "file"},
            {"name": "queue-001.json", "path": "jobs/queue-001.json", "sha": "good", "type": "file"},
        ]),
        FakeResponse(payload={"encoding": "base64", "content": "not-base64", "sha": "bad"}),
        content_response(job_payload(), "good"),
    ])

    pending = client.list_pending("HOME_DEV")

    assert [item.job.job_id for item in pending] == ["queue-001"]


def test_invalid_github_json_for_one_document_does_not_hide_a_later_valid_job():
    client, _ = queue([
        FakeResponse(payload=[
            {"name": "bad.json", "path": "jobs/bad.json", "sha": "bad", "type": "file"},
            {"name": "queue-001.json", "path": "jobs/queue-001.json", "sha": "good", "type": "file"},
        ]),
        FakeResponse(payload=ValueError("invalid response json"), text="not-json"),
        content_response(job_payload(), "good"),
    ])

    assert [item.job.job_id for item in client.list_pending("HOME_DEV")] == ["queue-001"]


def test_claim_lease_covers_long_handler_timeout_and_cleanup_margin():
    client, _ = queue([FakeResponse(payload={"content": {"sha": "new"}})])
    long_job = Job.model_validate(job_payload(timeout_seconds=7200))

    claimed = client.claim(long_job, "old", now=NOW)

    assert claimed.job.lease_expires_at >= NOW + timedelta(seconds=7260)
    assert not client._lease_is_stale(claimed.job, now=NOW + timedelta(seconds=7205))

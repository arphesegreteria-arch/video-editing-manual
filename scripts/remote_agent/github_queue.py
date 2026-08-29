"""Small, testable GitHub Contents API queue client."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Protocol
from urllib.parse import quote

from pydantic import ValidationError

from scripts.remote_agent.config import GitHubConfig
from scripts.remote_agent.logging_setup import redact_secrets
from scripts.remote_agent.models import Job, JobResult, JobStatus, MachineHeartbeat


REMOTE_LOG_MAX_BYTES = 256 * 1024
_TRUNCATION_MARKER = b"\n[TRUNCATED]\n"


class QueueError(RuntimeError):
    """Base class for sanitized queue failures."""


class InvalidJob(QueueError):
    """A remote job failed JSON, schema, or filename validation."""


class ClaimConflict(QueueError):
    """Another agent changed the job document before this claim."""


class LeaseActive(QueueError):
    """A claimed job still has an active lease."""


class NonRetryableJob(QueueError):
    """A stale job cannot safely be reclaimed."""


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        timeout: float,
    ) -> Any: ...


@dataclass(frozen=True)
class QueuedJob:
    job: Job
    sha: str


class GitHubQueue:
    def __init__(
        self,
        config: GitHubConfig,
        token: str,
        *,
        transport: HttpTransport | None = None,
        request_timeout_seconds: float = 15,
    ) -> None:
        if request_timeout_seconds <= 0:
            raise ValueError("request timeout must be positive")
        self.config = config
        self._token = token
        if transport is None:
            import requests

            transport = requests.Session()
        self._transport = transport
        self._timeout = request_timeout_seconds
        owner = quote(config.owner, safe="")
        repository = quote(config.repository, safe="")
        self._contents_url = f"{config.api_base_url.rstrip('/')}/repos/{owner}/{repository}/contents"
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        url = f"{self._contents_url}/{quote(path, safe='/')}"
        response = self._transport.request(
            method,
            url,
            headers=self._headers,
            json=payload,
            timeout=self._timeout,
        )
        if response.status_code not in expected:
            message = redact_secrets(
                f"GitHub {method} {path} failed ({response.status_code}): {response.text}",
                (self._token,),
            )
            raise QueueError(message)
        try:
            return response.json()
        except (TypeError, ValueError) as exc:
            raise QueueError(f"GitHub {method} {path} returned invalid JSON") from exc

    def list_pending(self, machine_id: str) -> list[QueuedJob]:
        listing = self._request(
            "GET",
            "jobs",
            payload=None,
            expected=(200,),
        )
        if not isinstance(listing, list):
            raise QueueError("GitHub jobs listing was not an array")
        pending: list[QueuedJob] = []
        for entry in sorted(listing, key=lambda item: str(item.get("path", "")).casefold()):
            if entry.get("type") != "file" or not str(entry.get("name", "")).endswith(".json"):
                continue
            path = str(entry.get("path", ""))
            document = self._request("GET", path, expected=(200,))
            job, sha = self._parse_job_document(document, expected_name=str(entry["name"]))
            if not job.matches_machine(machine_id):
                continue
            if job.status is JobStatus.PENDING or self._lease_is_stale(job):
                pending.append(QueuedJob(job=job, sha=sha))
        return pending

    @staticmethod
    def _parse_job_document(document: Any, *, expected_name: str) -> tuple[Job, str]:
        try:
            if not isinstance(document, dict) or document.get("encoding") != "base64":
                raise ValueError("unsupported content encoding")
            raw = base64.b64decode(document["content"], validate=True)
            payload = json.loads(raw.decode("utf-8"))
            job = Job.model_validate(payload)
            sha = str(document["sha"])
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise InvalidJob(f"invalid job document {expected_name}") from exc
        if expected_name != f"{job.job_id}.json":
            raise InvalidJob("job filename does not match job_id")
        return job, sha

    @staticmethod
    def _lease_is_stale(job: Job, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return (
            job.status in {JobStatus.CLAIMED, JobStatus.RUNNING}
            and job.lease_expires_at is not None
            and job.lease_expires_at <= current
        )

    def claim(
        self,
        job: Job,
        sha: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
        idempotent: bool = False,
    ) -> Job:
        current = now or datetime.now(timezone.utc)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if job.status is not JobStatus.PENDING:
            if not self._lease_is_stale(job, now=current):
                raise LeaseActive("job lease is still active")
            if not job.retryable or not idempotent:
                raise NonRetryableJob("stale job is not safe to retry")
        claimed = job.model_copy(update={
            "status": JobStatus.CLAIMED,
            "claimed_by": job.target_machine,
            "claimed_at": current,
            "lease_expires_at": current + timedelta(seconds=lease_seconds),
            "attempt": job.attempt + 1,
        })
        self._update_job(claimed, sha, message=f"Claim job {job.job_id}")
        return claimed

    def mark_running(self, job: Job, sha: str) -> Job:
        if job.status is not JobStatus.CLAIMED:
            raise QueueError("only a claimed job can be marked running")
        running = job.model_copy(update={"status": JobStatus.RUNNING})
        self._update_job(running, sha, message=f"Run job {job.job_id}")
        return running

    def _update_job(self, job: Job, sha: str, *, message: str) -> None:
        payload = self._file_payload(job.model_dump_json().encode("utf-8"), message=message, sha=sha)
        try:
            self._request("PUT", f"jobs/{job.job_id}.json", payload=payload, expected=(200, 201))
        except QueueError as exc:
            text = str(exc)
            if "(409)" in text or "(422)" in text:
                raise ClaimConflict("job document changed before update") from exc
            raise

    def write_result(self, result: JobResult) -> None:
        self._write_file(
            f"results/{result.job_id}.json",
            result.model_dump_json().encode("utf-8"),
            message=f"Write result {result.job_id}",
        )

    def write_log(self, job_id: str, log_text: str) -> None:
        raw = log_text.encode("utf-8", errors="replace")
        if len(raw) > REMOTE_LOG_MAX_BYTES:
            raw = raw[: REMOTE_LOG_MAX_BYTES - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
        self._write_file(f"logs/{job_id}.log", raw, message=f"Write log {job_id}")

    def write_heartbeat(self, heartbeat: MachineHeartbeat) -> None:
        self._write_file(
            f"machines/{heartbeat.machine_id}.json",
            heartbeat.model_dump_json().encode("utf-8"),
            message=f"Heartbeat {heartbeat.machine_id}",
        )

    def _write_file(self, path: str, content: bytes, *, message: str) -> None:
        self._request(
            "PUT",
            path,
            payload=self._file_payload(content, message=message),
            expected=(200, 201),
        )

    def _file_payload(self, content: bytes, *, message: str, sha: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.config.branch,
        }
        if sha is not None:
            payload["sha"] = sha
        return payload

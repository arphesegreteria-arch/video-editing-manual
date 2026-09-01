"""Small, testable GitHub Contents API queue client."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import re
from typing import Any, Protocol
from urllib.parse import quote

from pydantic import ValidationError

from scripts.remote_agent.config import GitHubConfig
from scripts.remote_agent.logging_setup import redact_secrets
from scripts.remote_agent.models import JOB_ID_PATTERN, Job, JobResult, JobStatus, MachineHeartbeat


REMOTE_LOG_MAX_BYTES = 256 * 1024
# A claim timestamp is recorded before the claim PUT.  Terminal persistence
# then needs a RUNNING PUT, a result GET+PUT and the terminal PUT.  Reserve at
# least five request timeouts, bounded cleanup time and scheduling jitter; five
# minutes is the minimum fail-safe window for the production 15-second client.
LEASE_CLEANUP_MARGIN_SECONDS = 300
_LEASE_FINALIZATION_REQUEST_COUNT = 5
_LEASE_LOCAL_CLEANUP_SECONDS = 30
_TRUNCATION_MARKER = b"\n[TRUNCATED]\n"
_JOB_ID_RE = re.compile(JOB_ID_PATTERN)


class QueueError(RuntimeError):
    """Base class for sanitized queue failures."""


class HttpError(QueueError):
    """A sanitized GitHub HTTP failure with a machine-readable status code."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        logger: logging.Logger | None = None,
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
        self._logger = logger
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
        _status, payload_value = self._request_with_status(
            method, path, payload=payload, expected=expected
        )
        return payload_value

    def _request_with_status(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> tuple[int, Any]:
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
            raise HttpError(response.status_code, message)
        try:
            return response.status_code, response.json()
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
        if any(
            not isinstance(entry, dict)
            or not all(isinstance(entry.get(field), str) and entry[field] for field in ("name", "path", "sha", "type"))
            for entry in listing
        ):
            raise InvalidJob("invalid GitHub jobs listing entry")
        pending: list[QueuedJob] = []
        for entry in sorted(listing, key=lambda item: item["path"].casefold()):
            if entry["type"] != "file" or not entry["name"].endswith(".json"):
                continue
            try:
                document = self._request("GET", entry["path"], expected=(200,))
                job, sha = self._parse_job_document(document, expected_name=entry["name"])
            except (InvalidJob, QueueError) as exc:
                if isinstance(exc, HttpError):
                    raise
                if self._logger is not None:
                    self._logger.warning("ignored one malformed queue job document")
                continue
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
            sha = document["sha"]
            if not isinstance(sha, str) or not sha:
                raise ValueError("invalid document SHA")
        except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, json.JSONDecodeError, ValidationError) as exc:
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
    ) -> QueuedJob:
        current = now or datetime.now(timezone.utc)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if job.status is not JobStatus.PENDING:
            if not self._lease_is_stale(job, now=current):
                raise LeaseActive("job lease is still active")
            if not job.retryable or not idempotent:
                raise NonRetryableJob("stale job is not safe to retry")
        finalization_margin = max(
            LEASE_CLEANUP_MARGIN_SECONDS,
            math.ceil(
                self._timeout * _LEASE_FINALIZATION_REQUEST_COUNT
                + _LEASE_LOCAL_CLEANUP_SECONDS
            ),
        )
        effective_lease_seconds = max(
            lease_seconds,
            job.timeout_seconds + finalization_margin,
        )
        claimed = job.model_copy(update={
            "status": JobStatus.CLAIMED,
            "claimed_by": job.target_machine,
            "claimed_at": current,
            "lease_expires_at": current + timedelta(seconds=effective_lease_seconds),
            "attempt": job.attempt + 1,
        })
        updated_sha = self._update_job(claimed, sha, message=f"Claim job {job.job_id}")
        return QueuedJob(job=claimed, sha=updated_sha)

    def mark_running(
        self,
        queued_job: QueuedJob,
        *,
        now: datetime | None = None,
    ) -> QueuedJob:
        job = queued_job.job
        if job.status is not JobStatus.CLAIMED:
            raise QueueError("only a claimed job can be marked running")
        current = now or datetime.now(timezone.utc)
        if job.lease_expires_at is None or job.lease_expires_at <= current:
            raise LeaseActive("job lease has expired")
        if job.claimed_by != job.target_machine:
            raise QueueError("job is not claimed by its target machine")
        running = job.model_copy(update={"status": JobStatus.RUNNING})
        updated_sha = self._update_job(running, queued_job.sha, message=f"Run job {job.job_id}")
        return QueuedJob(job=running, sha=updated_sha)

    def mark_terminal(self, queued_job: QueuedJob, status: JobStatus) -> QueuedJob:
        """Persist a terminal state only after the runner has held a valid running lease."""
        if queued_job.job.status is not JobStatus.RUNNING:
            raise QueueError("only a running job can be marked terminal")
        if status not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.FAILED_TIMEOUT, JobStatus.ABORTED}:
            raise QueueError("job status is not terminal")
        terminal = queued_job.job.model_copy(update={"status": status})
        updated_sha = self._update_job(terminal, queued_job.sha, message=f"Finish job {terminal.job_id}")
        return QueuedJob(job=terminal, sha=updated_sha)

    def _update_job(self, job: Job, sha: str, *, message: str) -> str:
        payload = self._file_payload(job.model_dump_json().encode("utf-8"), message=message, sha=sha)
        try:
            response = self._request("PUT", f"jobs/{job.job_id}.json", payload=payload, expected=(200, 201))
        except HttpError as exc:
            if exc.status_code in {409, 422}:
                raise ClaimConflict("job document changed before update") from exc
            raise
        try:
            updated_sha = response["content"]["sha"]
        except (KeyError, TypeError) as exc:
            raise QueueError("GitHub job update returned no response SHA") from exc
        if not isinstance(updated_sha, str) or not updated_sha:
            raise QueueError("GitHub job update returned an invalid response SHA")
        return updated_sha

    def write_result(self, result: JobResult) -> None:
        self._write_file(
            f"results/{result.job_id}.json",
            result.model_dump_json().encode("utf-8"),
            message=f"Write result {result.job_id}",
        )

    def write_log(self, job_id: str, log_text: str) -> None:
        if not _JOB_ID_RE.fullmatch(job_id):
            raise InvalidJob("invalid job_id for remote log")
        raw = redact_secrets(log_text, (self._token,)).encode("utf-8", errors="replace")
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
        status, document = self._request_with_status("GET", path, expected=(200, 404))
        sha: str | None = None
        if status == 404:
            sha = None
        elif isinstance(document, dict) and "sha" in document:
            candidate = document.get("sha")
            if not isinstance(candidate, str) or not candidate:
                raise QueueError(f"GitHub GET {path} returned an invalid blob SHA")
            sha = candidate
        else:
            raise QueueError(f"GitHub GET {path} returned an invalid content document")
        try:
            self._request(
                "PUT",
                path,
                payload=self._file_payload(content, message=message, sha=sha),
                expected=(200, 201),
            )
        except HttpError as exc:
            if exc.status_code in {409, 422}:
                raise ClaimConflict("output document changed before update") from exc
            raise

    def _file_payload(self, content: bytes, *, message: str, sha: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.config.branch,
        }
        if sha is not None:
            payload["sha"] = sha
        return payload

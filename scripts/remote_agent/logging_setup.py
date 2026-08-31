"""Redacted rotating log configuration for the ARPHE Remote Agent."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from typing import Iterable

from scripts.remote_agent.credentials import get_token_for_machine


LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
_AUTHORIZATION_PATTERN = re.compile(
    r"(Authorization\s*:\s*)(?:Bearer\s+)?[^,;\r\n]+", re.IGNORECASE
)
_AUTHORIZATION_MAPPING_PATTERN = re.compile(
    r"((?:['\"]authorization['\"])\s*:\s*['\"])(?:Bearer\s+)?[^'\"]+",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
_GITHUB_TOKEN_PATTERN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", re.IGNORECASE
)
_GENERIC_SECRET_QUOTED_ASSIGNMENT_PATTERN = re.compile(
    r"(\b(?:token|secret|password|credential|api[_-]?key)\b(?:['\"])?\s*[:=]\s*['\"])(?:Bearer\s+)?[^'\"]*",
    re.IGNORECASE,
)
_GENERIC_SECRET_PLAIN_ASSIGNMENT_PATTERN = re.compile(
    r"(\b(?:token|secret|password|credential|api[_-]?key)\b\s*[:=]\s*)(?:Bearer\s+)?[^,;\r\n]+",
    re.IGNORECASE,
)


def redact_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace known and recognizable authentication values with a safe marker."""
    redacted = text
    for secret in sorted((secret for secret in secrets if secret), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _AUTHORIZATION_MAPPING_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    redacted = _GITHUB_TOKEN_PATTERN.sub("[REDACTED]", redacted)
    redacted = _GENERIC_SECRET_QUOTED_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", redacted)
    return _GENERIC_SECRET_PLAIN_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", redacted)


class _RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self._secrets = tuple(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record), self._secrets)


class _RedactingHandler(logging.Handler):
    """Render a record safely before handing it to an untrusted backend."""

    def __init__(self, backend: logging.Handler, secrets: Iterable[str]) -> None:
        super().__init__(backend.level)
        self._backend = backend
        self.setFormatter(_RedactingFormatter(secrets))

    @property
    def backend(self) -> logging.Handler:
        return self._backend

    def emit(self, record: logging.LogRecord) -> None:
        rendered = self.format(record)
        safe_record = logging.LogRecord(
            name=record.name,
            level=record.levelno,
            pathname="",
            lineno=0,
            msg=rendered,
            args=(),
            exc_info=None,
        )
        self._backend.handle(safe_record)

    def flush(self) -> None:
        self._backend.flush()

    def close(self) -> None:
        try:
            self._backend.close()
        finally:
            super().close()


def configure_redacting_logger(
    logger: logging.Logger,
    handlers: Iterable[logging.Handler],
    *,
    secrets: Iterable[str] = (),
) -> logging.Logger:
    """Apply the central redaction/no-propagation contract to injected backends."""
    configured_handlers = tuple(handlers)
    configured_secrets = tuple(secrets)
    if not configured_handlers:
        raise ValueError("a redacting logger requires at least one handler")
    logger.setLevel(logging.INFO)
    logger.disabled = False
    logger.propagate = False
    for existing_handler in logger.handlers[:]:
        logger.removeHandler(existing_handler)
        existing_handler.close()
    logger.filters.clear()
    for handler in configured_handlers:
        logger.addHandler(_RedactingHandler(handler, configured_secrets))
    return logger


def is_redacting_logger(logger: object) -> bool:
    """Return whether every possible local output path applies central redaction."""
    return (
        type(logger) is logging.Logger
        and not logger.disabled
        and logger.isEnabledFor(logging.ERROR)
        and not logger.propagate
        and not logger.filters
        and bool(logger.handlers)
        and all(
            type(handler) is _RedactingHandler
            and type(handler.formatter) is _RedactingFormatter
            and not handler.filters
            and "emit" not in handler.__dict__
            and "handle" not in handler.__dict__
            for handler in logger.handlers
        )
        and any(handler.level <= logging.ERROR for handler in logger.handlers)
    )


def require_redacting_logger(logger: object, machine_id: str) -> logging.Logger:
    """Fail closed unless a machine's logger has verified central redaction wiring."""
    expected_name = f"arphe.remote_agent.{machine_id}"
    if not is_redacting_logger(logger) or logger.name != expected_name:
        raise ValueError(
            f"logger must be the centrally configured redacting logger {expected_name!r}"
        )
    return logger


def configure_logging(machine_id: str) -> logging.Logger:
    """Create a machine-local rotating logger with centralized secret redaction."""
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    log_directory = local_app_data / "ARPHE" / "RemoteAgent" / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"arphe.remote_agent.{machine_id}")
    handler = RotatingFileHandler(
        log_directory / f"{machine_id}.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    token = get_token_for_machine(machine_id)
    return configure_redacting_logger(
        logger,
        [handler],
        secrets=(token,) if token else (),
    )

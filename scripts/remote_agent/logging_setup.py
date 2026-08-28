"""Redacted rotating log configuration for the ARPHE Remote Agent."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from typing import Iterable


LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
_AUTHORIZATION_PATTERN = re.compile(
    r"(Authorization\s*:\s*)(?:Bearer\s+)?[^\s,;]+", re.IGNORECASE
)
_BEARER_PATTERN = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
_GITHUB_TOKEN_PATTERN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", re.IGNORECASE
)


def redact_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace known and recognizable authentication values with a safe marker."""
    redacted = text
    for secret in sorted((secret for secret in secrets if secret), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    return _GITHUB_TOKEN_PATTERN.sub("[REDACTED]", redacted)


class _RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self._secrets = tuple(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record), self._secrets)


def configure_logging(
    machine_id: str, secrets: Iterable[str] = ()
) -> logging.Logger:
    """Create a machine-local rotating logger with centralized secret redaction."""
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    log_directory = local_app_data / "ARPHE" / "RemoteAgent" / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"arphe.remote_agent.{machine_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for existing_handler in logger.handlers[:]:
        logger.removeHandler(existing_handler)
        existing_handler.close()

    handler = RotatingFileHandler(
        log_directory / f"{machine_id}.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(_RedactingFormatter(secrets))
    logger.addHandler(handler)
    return logger

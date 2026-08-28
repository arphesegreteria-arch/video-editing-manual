import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from scripts.remote_agent.logging_setup import configure_logging, redact_secrets


TOKEN = "unit-test-token-value"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"token={TOKEN}", "token=[REDACTED]"),
        (f"Authorization: Bearer {TOKEN}", "Authorization: [REDACTED]"),
    ],
)
def test_redact_secrets_removes_tokens_and_authorization_values(
    text: str, expected: str
) -> None:
    """Catches logs retaining a token directly or in an Authorization header."""
    assert redact_secrets(text, [TOKEN]) == expected


def test_configured_logger_redacts_token_from_exception_traceback(tmp_path, monkeypatch) -> None:
    """Catches exception logging that leaks an authenticated request token."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    logger = configure_logging("HOME_DEV", secrets=[TOKEN])

    try:
        raise RuntimeError(f"GitHub rejected Authorization: Bearer {TOKEN}")
    except RuntimeError:
        logger.exception("queue request failed")
    finally:
        for handler in logger.handlers:
            handler.flush()

    handler = next(handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler))
    content = Path(handler.baseFilename).read_text(encoding="utf-8")

    assert TOKEN not in content
    assert "[REDACTED]" in content
    assert handler.maxBytes == 5 * 1024 * 1024
    assert handler.backupCount == 5
    assert handler.baseFilename.endswith("ARPHE\\RemoteAgent\\logs\\HOME_DEV.log")

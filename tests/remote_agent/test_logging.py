import logging
from logging.handlers import RotatingFileHandler
from io import StringIO
from pathlib import Path

import pytest

from scripts.remote_agent import logging_setup
from scripts.remote_agent.logging_setup import (
    configure_logging,
    configure_redacting_logger,
    is_redacting_logger,
    redact_secrets,
)


TOKEN = "unit-test-token-value"
LEGACY_TOKEN = "legacy-opaque-token"


def test_injected_logger_backend_is_centrally_redacted_without_credentials() -> None:
    """Catches test/injected loggers bypassing the same formatter contract as production."""
    stream = StringIO()
    logger = logging.Logger("arphe.remote_agent.HOME_DEV")
    handler = logging.StreamHandler(stream)

    configured = configure_redacting_logger(logger, [handler], secrets=[TOKEN])
    configured.error("request token=%s", TOKEN)

    assert configured is logger
    assert is_redacting_logger(configured)
    assert configured.propagate is False
    assert TOKEN not in stream.getvalue()
    assert "token=[REDACTED]" in stream.getvalue()


def test_every_injected_backend_receives_the_complete_known_secret_set() -> None:
    """Catches a one-shot secrets iterable protecting only the first configured handler."""
    streams = [StringIO(), StringIO()]
    logger = logging.Logger("arphe.remote_agent.HOME_DEV")

    configure_redacting_logger(
        logger,
        [logging.StreamHandler(stream) for stream in streams],
        secrets=(secret for secret in [TOKEN]),
    )
    logger.error("authenticated as %s", TOKEN)

    assert all(TOKEN not in stream.getvalue() for stream in streams)
    assert all("[REDACTED]" in stream.getvalue() for stream in streams)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"token={TOKEN}", "token=[REDACTED]"),
        (f"Authorization: Bearer {TOKEN}", "Authorization: [REDACTED]"),
        (
            f"{{'Authorization': '{LEGACY_TOKEN}'}}",
            "{'Authorization': '[REDACTED]'}",
        ),
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
    monkeypatch.setattr(logging_setup, "get_token_for_machine", lambda machine_id: TOKEN)
    logger = configure_logging("HOME_DEV")

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


def test_default_logger_redacts_opaque_token_in_mapping_style_header(
    tmp_path, monkeypatch
) -> None:
    """Catches default logging leaking legacy tokens in request-header mappings."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(
        logging_setup,
        "get_token_for_machine",
        lambda machine_id: LEGACY_TOKEN,
        raising=False,
    )
    logger = configure_logging("HOME_DEV")

    logger.error("request headers: %s", {"Authorization": LEGACY_TOKEN})
    for handler in logger.handlers:
        handler.flush()

    handler = next(handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler))
    content = Path(handler.baseFilename).read_text(encoding="utf-8")

    assert LEGACY_TOKEN not in content
    assert "[REDACTED]" in content

"""Shared cooperative-cancellation contract for side-effecting agent work."""

from __future__ import annotations

import threading


class CancellationRequested(RuntimeError):
    """Raised at a safe boundary before or after a side effect."""


class CancellationToken:
    """Thread-safe cooperative cancellation signal passed to mutating adapters."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def require_not_cancelled(token: CancellationToken) -> None:
    """Reject work at a defined safe boundary once cancellation has been requested."""
    if token.cancelled:
        raise CancellationRequested("operation cancelled")

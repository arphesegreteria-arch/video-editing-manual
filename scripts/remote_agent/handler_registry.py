"""Registry of locally installed handlers and their approved schemas."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class RegisteredHandler:
    action: str
    schema: type[BaseModel]
    handler: Callable[..., Any]
    idempotent: bool


class HandlerRegistry:
    def __init__(self, allowed_actions: Iterable[str]) -> None:
        self._allowed_actions = frozenset(allowed_actions)
        self._handlers: dict[str, RegisteredHandler] = {}

    def register(
        self,
        action: str,
        schema: type[BaseModel],
        handler: Callable[..., Any],
        idempotent: bool = False,
    ) -> None:
        if action in self._handlers:
            raise ValueError(f"handler already registered for action: {action}")
        self._handlers[action] = RegisteredHandler(action, schema, handler, idempotent)

    def is_enabled(self, action: str) -> bool:
        return action in self._allowed_actions

    def get(self, action: str) -> RegisteredHandler:
        try:
            registered = self._handlers[action]
        except KeyError as exc:
            raise KeyError(f"no handler registered for action: {action}") from exc
        if not self.is_enabled(action):
            raise PermissionError(f"action is not enabled in the local profile: {action}")
        return registered

    def validate_parameters(self, action: str, parameters: dict[str, Any]) -> BaseModel:
        return self.get(action).schema.model_validate(parameters)

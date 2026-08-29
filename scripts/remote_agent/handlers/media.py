"""Schemas and handlers that keep media access behind the local broker."""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Literal

from pydantic import Field, field_validator

from scripts.remote_agent.models import StrictModel


FolderAlias = Literal["incoming", "test_media", "workspace", "exports"]


def _relative_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = PureWindowsPath(value)
    if path.is_absolute() or path.drive or value.startswith(("/", "\\")) or ".." in path.parts:
        raise ValueError("path must be relative to its configured folder alias")
    return value


class ListMediaParameters(StrictModel):
    alias: FolderAlias
    relative_dir: str = ""

    _validate_relative_dir = field_validator("relative_dir")(_relative_path)


class FindMediaParameters(StrictModel):
    alias: FolderAlias
    query: str = Field(min_length=1, max_length=256)


class HashMediaParameters(StrictModel):
    alias: FolderAlias
    relative_path: str = Field(min_length=1, max_length=1024)

    _validate_relative_path = field_validator("relative_path")(_relative_path)


class CopyToWorkspaceParameters(StrictModel):
    source_alias: FolderAlias
    relative_path: str = Field(min_length=1, max_length=1024)
    destination_relative_path: str | None = Field(default=None, max_length=1024)

    _validate_relative_path = field_validator("relative_path")(_relative_path)
    _validate_destination = field_validator("destination_relative_path")(_relative_path)


class ImportMediaParameters(StrictModel):
    source_alias: FolderAlias
    relative_path: str = Field(min_length=1, max_length=1024)
    target_bin: str | None = Field(default=None, max_length=256)

    _validate_relative_path = field_validator("relative_path")(_relative_path)


def list_media(parameters: ListMediaParameters, broker: object) -> dict[str, object]:
    return {"media": getattr(broker, "list_media")(parameters.alias, parameters.relative_dir)}


def find_media(parameters: FindMediaParameters, broker: object) -> dict[str, object]:
    return {"media": getattr(broker, "find_media")(parameters.alias, parameters.query)}


def hash_media(parameters: HashMediaParameters, broker: object) -> dict[str, object]:
    return dict(getattr(broker, "hash_media")(parameters.alias, parameters.relative_path))


def copy_to_workspace(parameters: CopyToWorkspaceParameters, broker: object) -> dict[str, object]:
    path = getattr(broker, "copy_to_workspace")(
        parameters.source_alias, parameters.relative_path, parameters.destination_relative_path
    )
    return {"path": path}


def import_media(parameters: ImportMediaParameters, broker: object, resolve_manager: object) -> dict[str, object]:
    # Hashing is the broker's guarded file check; no raw local path leaves the handler.
    media = getattr(broker, "hash_media")(parameters.source_alias, parameters.relative_path)
    getattr(resolve_manager, "require_test_project")()
    return dict(getattr(resolve_manager, "import_media")(media["path"], parameters.target_bin))

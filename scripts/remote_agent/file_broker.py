"""Guarded access to configured local media folders."""

from __future__ import annotations

import hashlib
import ntpath
import os
from pathlib import Path, PureWindowsPath
import shutil
from typing import Callable

from scripts.remote_agent.config import FolderConfig


ReparsePointDetector = Callable[[Path], bool]
MEDIA_EXTENSIONS = frozenset(
    {
        ".mov",
        ".mp4",
        ".m4v",
        ".wav",
        ".mp3",
        ".aif",
        ".aiff",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
    }
)
_HASH_CHUNK_SIZE = 1024 * 1024
_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


def _has_reparse_attribute(path: Path) -> bool:
    """Return whether an existing Windows path has the reparse-point attribute."""
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & 0x400)


class FileBroker:
    def __init__(
        self,
        folders: FolderConfig,
        *,
        is_reparse_point: ReparsePointDetector | None = None,
    ) -> None:
        self._folders = folders
        self._is_reparse_point = is_reparse_point or _has_reparse_attribute

    @staticmethod
    def _relative_parts(relative_path: str) -> tuple[str, ...]:
        if not isinstance(relative_path, str) or "\x00" in relative_path:
            raise ValueError("path must be a valid relative path")

        windows_path = PureWindowsPath(relative_path)
        if (
            windows_path.is_absolute()
            or bool(windows_path.drive)
            or relative_path.startswith(("/", "\\"))
            or ":" in relative_path
        ):
            raise ValueError("jobs must provide a relative path")

        parts = tuple(
            part for part in relative_path.replace("/", "\\").split("\\") if part
        )
        if ".." in parts:
            raise ValueError("parent traversal is not allowed")
        if any(
            part.rstrip(" .").split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES
            for part in parts
        ):
            raise ValueError("jobs must provide a relative path, not a device path")
        return tuple(part for part in parts if part != ".")

    @staticmethod
    def _is_within(root: Path, candidate: Path) -> bool:
        normalized_root = ntpath.normcase(ntpath.normpath(str(root)))
        normalized_candidate = ntpath.normcase(ntpath.normpath(str(candidate)))
        try:
            return ntpath.commonpath((normalized_root, normalized_candidate)) == normalized_root
        except ValueError:
            return False

    def _reject_reparse_components(self, root: Path, parts: tuple[str, ...]) -> None:
        current = root
        for part in parts:
            current /= part
            if current.is_symlink() or self._is_reparse_point(current):
                raise PermissionError("path contains a symlink or reparse point")

    def resolve(self, alias: str, relative_path: str) -> Path:
        root = self._folders.path_for(alias)
        parts = self._relative_parts(relative_path)
        self._reject_reparse_components(root, parts)

        resolved_root = root.resolve(strict=False)
        candidate = root.joinpath(*parts).resolve(strict=False)
        if not self._is_within(resolved_root, candidate):
            raise PermissionError("resolved path escapes the configured folder")
        return candidate

    def _alias_relative(self, alias: str, path: Path) -> str:
        root = self._folders.path_for(alias).resolve(strict=False)
        relative = ntpath.relpath(str(path), str(root))
        if relative == "." or relative.startswith(("..\\", "../")):
            raise PermissionError("path cannot be represented below the configured alias")
        return f"{alias}/{PureWindowsPath(relative).as_posix()}"

    @staticmethod
    def _require_media_extension(path: Path) -> None:
        if path.suffix.casefold() not in MEDIA_EXTENSIONS:
            raise ValueError("unsupported media extension")

    def _require_media_file(self, alias: str, relative_path: str) -> Path:
        path = self.resolve(alias, relative_path)
        self._require_media_extension(path)
        if not path.is_file():
            raise FileNotFoundError(f"media file does not exist: {alias}/{relative_path}")
        return path

    def _walk_media(self, alias: str, directory: Path) -> list[Path]:
        root = self._folders.path_for(alias).resolve(strict=False)
        pending = [directory]
        media: list[Path] = []
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                children = sorted(entries, key=lambda entry: (entry.name.casefold(), entry.name))
            for entry in children:
                relative = ntpath.relpath(entry.path, str(root))
                resolved = self.resolve(alias, relative)
                if resolved.is_dir():
                    pending.append(resolved)
                elif resolved.is_file() and resolved.suffix.casefold() in MEDIA_EXTENSIONS:
                    media.append(resolved)
        return media

    def list_media(self, alias: str, relative_dir: str = "") -> list[str]:
        directory = self.resolve(alias, relative_dir)
        if not directory.is_dir():
            raise NotADirectoryError(
                f"media directory does not exist: {alias}/{relative_dir}"
            )
        media = (self._alias_relative(alias, path) for path in self._walk_media(alias, directory))
        return sorted(media, key=lambda value: (value.casefold(), value))

    def find_media(self, alias: str, query: str) -> list[str]:
        if not isinstance(query, str) or not query:
            raise ValueError("media query must not be empty")
        folded_query = query.casefold()
        return [
            alias_relative
            for alias_relative in self.list_media(alias)
            if folded_query in PureWindowsPath(alias_relative).name.casefold()
        ]

    def hash_media(self, alias: str, relative_path: str) -> dict[str, str | int]:
        path = self._require_media_file(alias, relative_path)
        digest = hashlib.sha256()
        size_bytes = 0
        with path.open("rb") as media_file:
            while chunk := media_file.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
                size_bytes += len(chunk)
        return {
            "path": self._alias_relative(alias, path),
            "size_bytes": size_bytes,
            "sha256": digest.hexdigest(),
        }

    def copy_to_workspace(
        self,
        source_alias: str,
        relative_path: str,
        destination_relative_path: str | None = None,
    ) -> str:
        source = self._require_media_file(source_alias, relative_path)
        destination_relative_path = destination_relative_path or source.name
        destination = self.resolve("workspace", destination_relative_path)
        self._require_media_extension(destination)
        if destination.is_dir():
            raise IsADirectoryError("workspace destination is a directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = self.resolve("workspace", destination_relative_path)
        shutil.copy2(source, destination)
        return self._alias_relative("workspace", destination)

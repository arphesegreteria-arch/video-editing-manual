from __future__ import annotations

from pathlib import Path

import pytest

from scripts.remote_agent.config import FolderConfig
from scripts.remote_agent.file_broker import FileBroker


def folder_config(tmp_path: Path) -> FolderConfig:
    roots = {
        alias: tmp_path / alias
        for alias in ("incoming", "test_media", "workspace", "exports")
    }
    for root in roots.values():
        root.mkdir()
    return FolderConfig(**roots)


def test_resolve_accepts_a_relative_path_below_the_configured_alias(tmp_path) -> None:
    """Catches valid alias-relative paths being blocked by the broker boundary."""
    broker = FileBroker(folder_config(tmp_path))

    resolved = broker.resolve("incoming", "shoot/day-01/clip.mov")

    assert resolved == (tmp_path / "incoming/shoot/day-01/clip.mov").resolve()


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.mov",
        "shoot/../../outside.mov",
        r"shoot\..\..\outside.mov",
    ],
)
def test_resolve_rejects_parent_traversal(tmp_path, unsafe_path: str) -> None:
    """Catches parent components that could escape an allowed folder root."""
    broker = FileBroker(folder_config(tmp_path))

    with pytest.raises(ValueError, match="parent traversal"):
        broker.resolve("incoming", unsafe_path)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/outside.mov",
        r"\outside.mov",
        r"C:\outside.mov",
        r"C:outside.mov",
        r"\\server\share\outside.mov",
        r"\\?\C:\outside.mov",
        r"\\.\PhysicalDrive0",
        "NUL.mp4",
        "folder/CON.mov",
        "file:///C:/outside.mov",
        "https://example.invalid/outside.mov",
    ],
)
def test_resolve_rejects_absolute_drive_device_and_uri_paths(
    tmp_path, unsafe_path: str
) -> None:
    """Catches remote jobs supplying non-relative Windows or URI path forms."""
    broker = FileBroker(folder_config(tmp_path))

    with pytest.raises(ValueError, match="relative path"):
        broker.resolve("incoming", unsafe_path)


def test_resolve_uses_case_insensitive_windows_containment(tmp_path) -> None:
    """Catches false containment failures caused only by Windows path casing."""
    config = folder_config(tmp_path)
    differently_cased = Path(str(config.incoming).swapcase())
    config = config.model_copy(update={"incoming": differently_cased})
    broker = FileBroker(config)

    resolved = broker.resolve("incoming", "clip.mov")

    assert str(resolved).casefold() == str(config.incoming / "clip.mov").casefold()


def test_resolve_rejects_a_reparse_point_component(tmp_path) -> None:
    """Catches a Windows junction redirecting an allowed path outside its root."""
    config = folder_config(tmp_path)
    junction = config.incoming / "junction"
    junction.mkdir()
    broker = FileBroker(
        config,
        is_reparse_point=lambda path: path.name.casefold() == "junction",
    )

    with pytest.raises(PermissionError, match="reparse point"):
        broker.resolve("incoming", "junction/secret.mov")


def test_resolve_rejects_a_real_symlink_escape_when_supported(tmp_path) -> None:
    """Catches a filesystem symlink redirecting an allowed path outside its root."""
    config = folder_config(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = config.incoming / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"test host cannot create directory symlinks: {exc}")
    broker = FileBroker(config)

    with pytest.raises(PermissionError, match="symlink"):
        broker.resolve("incoming", "linked/secret.mov")


def test_list_media_filters_extensions_and_returns_sorted_alias_paths(tmp_path) -> None:
    """Catches unsupported files, absolute path leakage, and unstable listing order."""
    config = folder_config(tmp_path)
    (config.incoming / "nested").mkdir()
    (config.incoming / "Z-last.WAV").write_bytes(b"audio")
    (config.incoming / "alpha.mp4").write_bytes(b"video")
    (config.incoming / "nested/Beta.JPEG").write_bytes(b"image")
    (config.incoming / "notes.txt").write_text("not media", encoding="utf-8")
    broker = FileBroker(config)

    media = broker.list_media("incoming", ".")

    assert media == [
        "incoming/alpha.mp4",
        "incoming/nested/Beta.JPEG",
        "incoming/Z-last.WAV",
    ]


@pytest.mark.parametrize(
    "extension",
    [
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
    ],
)
def test_list_media_accepts_each_v1_media_extension(tmp_path, extension: str) -> None:
    """Catches removal of a media type explicitly allowed by the V1 design."""
    config = folder_config(tmp_path)
    filename = f"sample{extension}"
    (config.test_media / filename).write_bytes(b"media")
    broker = FileBroker(config)

    assert broker.list_media("test_media", "") == [f"test_media/{filename}"]


def test_find_media_searches_filenames_case_insensitively(tmp_path) -> None:
    """Catches filename search that is case-sensitive or returns unsupported files."""
    config = folder_config(tmp_path)
    (config.test_media / "take-ALPHA-01.mov").write_bytes(b"one")
    (config.test_media / "take-alpha-02.png").write_bytes(b"two")
    (config.test_media / "take-alpha-notes.txt").write_bytes(b"three")
    broker = FileBroker(config)

    found = broker.find_media("test_media", "Alpha")

    assert found == [
        "test_media/take-ALPHA-01.mov",
        "test_media/take-alpha-02.png",
    ]


def test_hash_media_streams_sha256_and_returns_alias_relative_metadata(tmp_path) -> None:
    """Catches hashing the wrong bytes or exposing an absolute source path."""
    config = folder_config(tmp_path)
    (config.incoming / "clip.mp4").write_bytes(b"abc")
    broker = FileBroker(config)

    result = broker.hash_media("incoming", "clip.mp4")

    assert result == {
        "path": "incoming/clip.mp4",
        "size_bytes": 3,
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    }


def test_hash_media_rejects_an_unsupported_extension(tmp_path) -> None:
    """Catches non-media files crossing the broker through the hash operation."""
    config = folder_config(tmp_path)
    (config.incoming / "secrets.txt").write_text("not media", encoding="utf-8")
    broker = FileBroker(config)

    with pytest.raises(ValueError, match="unsupported media extension"):
        broker.hash_media("incoming", "secrets.txt")


def test_copy_to_workspace_copies_media_and_returns_only_workspace_alias(tmp_path) -> None:
    """Catches copies outside workspace or results that disclose local absolute paths."""
    config = folder_config(tmp_path)
    (config.incoming / "source.mov").write_bytes(b"video-bytes")
    broker = FileBroker(config)

    copied = broker.copy_to_workspace(
        "incoming", "source.mov", "job-001/copied.mov"
    )

    assert copied == "workspace/job-001/copied.mov"
    assert (config.workspace / "job-001/copied.mov").read_bytes() == b"video-bytes"

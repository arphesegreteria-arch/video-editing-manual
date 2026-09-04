from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


CAPABILITY_NAMES = (
    "CAP_PROJECT", "CAP_TIMELINE", "CAP_FUSION", "CAP_REVIEW",
    "CAP_MOTION", "CAP_ASSETS", "CAP_RENDER",
)

DEFAULT_PALETTE = {
    "ivory": "#F7F2E8",
    "cream": "#EFE3CF",
    "beige": "#D7C2A6",
    "burgundy": "#6C2438",
    "warm_brown": "#8A6248",
    "dark_brown": "#3A2923",
    "black": "#111111",
    "white": "#FFFFFF",
}

DEFAULT_FLAGS = {
    "CAP_PROJECT": True,
    "CAP_TIMELINE": True,
    "CAP_FUSION": False,
    "CAP_REVIEW": False,
    "CAP_MOTION": False,
    "CAP_ASSETS": False,
    "CAP_RENDER": False,
}

ALLOWED_RENDER_PAIRS = {("mp4", "H264")}


def _default_config_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA non disponibile; impostare ARPHE_CREATIVE_CONFIG.")
    return Path(local) / "ARPHE" / "CreativeBridge03" / "creative_config.json"


@dataclass(frozen=True)
class CreativeConfig:
    path: Path
    asset_root: Path
    render_root: Path
    state_path: Path
    audit_log_path: Path
    palette: dict[str, str]
    flags: dict[str, bool]
    allowed_projects: frozenset[str]
    allowed_timelines: frozenset[str]
    render_format: str
    render_codec: str


def _path(value: str, base: Path) -> Path:
    return Path(os.path.expandvars(value)).expanduser().resolve() if value else base.resolve()


def load_config(path: Path | None = None) -> CreativeConfig:
    selected = path or Path(os.environ.get("ARPHE_CREATIVE_CONFIG", "") or _default_config_path())
    selected = selected.expanduser().resolve()
    if not selected.is_file():
        raise FileNotFoundError(
            f"Config creative non trovata: {selected}. Copiare creative_config.example.json senza aggiungere segreti."
        )
    raw: dict[str, Any] = json.loads(selected.read_text(encoding="utf-8-sig"))
    if raw.get("runtime_id") != "ARPHE_MCP_BRIDGE_CREATIVE_03":
        raise ValueError("runtime_id config non valido")
    if raw.get("workstation_id") != "PC_SEGRETERIA":
        raise ValueError("Questa build è limitata a PC_SEGRETERIA")
    flags_raw = raw.get("feature_flags", {})
    if not isinstance(flags_raw, dict):
        raise ValueError("feature_flags deve essere un oggetto JSON")
    unknown_flags = set(flags_raw) - set(CAPABILITY_NAMES)
    if unknown_flags:
        raise ValueError(f"Feature flag sconosciute: {sorted(unknown_flags)}")
    if any(not isinstance(value, bool) for value in flags_raw.values()):
        raise ValueError("Ogni feature flag deve essere true o false")
    flags = {name: flags_raw.get(name, DEFAULT_FLAGS[name]) for name in CAPABILITY_NAMES}
    palette = dict(DEFAULT_PALETTE)
    palette.update(raw.get("palette", {}))
    from .safety import validate_palette
    validate_palette(palette)
    base = selected.parent
    render_format = str(raw.get("render_format", "mp4"))
    render_codec = str(raw.get("render_codec", "H264"))
    if (render_format, render_codec) not in ALLOWED_RENDER_PAIRS:
        raise ValueError("Coppia render_format/render_codec non consentita")
    return CreativeConfig(
        path=selected,
        asset_root=_path(str(raw.get("asset_root", "")), base / "assets"),
        render_root=_path(str(raw.get("render_root", "")), base / "renders"),
        state_path=_path(str(raw.get("state_path", "")), base / "creative_state.json"),
        audit_log_path=_path(str(raw.get("audit_log_path", "")), base / "audit.jsonl"),
        palette=palette,
        flags=flags,
        allowed_projects=frozenset(str(v) for v in raw.get("allowed_projects", [])),
        allowed_timelines=frozenset(str(v) for v in raw.get("allowed_timelines", [])),
        render_format=render_format,
        render_codec=render_codec,
    )

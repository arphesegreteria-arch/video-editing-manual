from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
from typing import Any


CAPABILITY_NAMES = (
    "CAP_PROJECT", "CAP_TIMELINE", "CAP_FUSION", "CAP_REVIEW",
    "CAP_MOTION", "CAP_ASSETS", "CAP_RENDER", "CAP_LONGFORM", "CAP_CLEANUP",
    "CAP_ARTIFACT_MAINTENANCE",
    "CAP_RESOLVE_RETIREMENT",
    "CAP_READABILITY_GUARD",
    "CAP_EDITORIAL_SELECTION",
    "CAP_CARABELLESE_CLEANUP",
    "CAP_VERTICAL_SOCIAL",
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
    "CAP_LONGFORM": False,
    "CAP_CLEANUP": False,
    "CAP_ARTIFACT_MAINTENANCE": False,
    "CAP_RESOLVE_RETIREMENT": False,
    "CAP_READABILITY_GUARD": False,
    "CAP_EDITORIAL_SELECTION": False,
    "CAP_CARABELLESE_CLEANUP": False,
    "CAP_VERTICAL_SOCIAL": False,
}

ALLOWED_RENDER_PAIRS = {("mp4", "H264"), ("mov", "ProRes422HQ")}


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
    media_roots: tuple[Path, ...] = ()
    transcript_root: Path = Path(".")
    audio_root: Path = Path(".")
    audio_jobs_root: Path = Path(".")
    workstation_id: str = "PC_UNSPECIFIED"
    workflow_registry_path: Path = Path("editorial_workflows.json")
    render_profile_registry_path: Path = Path("render_profiles.json")
    artifact_policy_path: Path = Path("artifact_retention.json")
    artifact_registry_path: Path = Path("artifact_registry.json")
    runtime_log_root: Path = Path("runtime-logs")
    resolve_archive_root: Path = Path("resolve-archives")
    resolve_retirement_registry_path: Path = Path("resolve-retirements.json")
    editorial_jobs_path: Path = Path("editorial_jobs.json")
    editorial_journal_path: Path = Path("editorial_journal.jsonl")
    editorial_profile_overlay_path: Path = Path("editorial_profile_overlay.json")
    editorial_profile_proposals_path: Path = Path("editorial_profile_proposals.json")
    carabellese_jobs_path: Path = Path("carabellese_jobs.json")
    carabellese_journal_path: Path = Path("carabellese_journal.jsonl")
    carabellese_profile_overlay_path: Path = Path("carabellese_profile_overlay.json")
    carabellese_profile_proposals_path: Path = Path("carabellese_profile_proposals.json")
    carabellese_checkpoint_root: Path = Path("carabellese-checkpoints")
    vertical_social_plans_path: Path = Path("vertical_social_plans.json")
    vertical_social_journal_path: Path = Path("vertical_social_journal.jsonl")


def _path(value: str, base: Path) -> Path:
    return Path(os.path.expandvars(value)).expanduser().resolve() if value else base.resolve()


def _registry_path(value: object, package_default: Path) -> Path:
    if not value:
        return package_default.resolve()
    selected = Path(os.path.expandvars(str(value))).expanduser()
    return (selected if selected.is_absolute() else package_default.parent / selected).resolve()


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
    if not re.fullmatch(r"PC_[A-Z0-9_]{2,48}", str(raw.get("workstation_id", ""))):
        raise ValueError("workstation_id non valido: usare PC_ seguito da lettere, numeri o underscore")
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
    package_root = Path(__file__).resolve().parents[1]
    render_format = str(raw.get("render_format", "mp4"))
    render_codec = str(raw.get("render_codec", "H264"))
    if (render_format, render_codec) not in ALLOWED_RENDER_PAIRS:
        raise ValueError("Coppia render_format/render_codec non consentita")
    state_path = _path(str(raw.get("state_path", "")), base / "creative_state.json")
    editorial_root = state_path.parent
    return CreativeConfig(
        path=selected,
        asset_root=_path(str(raw.get("asset_root", "")), base / "assets"),
        render_root=_path(str(raw.get("render_root", "")), base / "renders"),
        state_path=state_path,
        audit_log_path=_path(str(raw.get("audit_log_path", "")), base / "audit.jsonl"),
        palette=palette,
        flags=flags,
        allowed_projects=frozenset(str(v) for v in raw.get("allowed_projects", [])),
        allowed_timelines=frozenset(str(v) for v in raw.get("allowed_timelines", [])),
        render_format=render_format,
        render_codec=render_codec,
        media_roots=tuple(_path(str(v), base) for v in raw.get(
            "media_roots", [str(Path(os.environ.get("USERPROFILE", "C:/Users/auras")) / "Downloads")]
        )),
        transcript_root=_path(str(raw.get("transcript_root", "")),
                              Path(os.environ.get("LOCALAPPDATA", str(base))) / "ARPHE" / "Longform04" / "transcripts"),
        audio_root=_path(str(raw.get("audio_root", "")),
                         Path(os.environ.get("LOCALAPPDATA", str(base))) / "ARPHE" / "Longform04" / "audio"),
        audio_jobs_root=_path(str(raw.get("audio_jobs_root", "")),
                              Path(os.environ.get("LOCALAPPDATA", str(base))) / "ARPHE" / "Longform04" / "audio_jobs"),
        workstation_id=str(raw["workstation_id"]),
        workflow_registry_path=_registry_path(raw.get("workflow_registry_path"), package_root / "editorial_workflows.json"),
        render_profile_registry_path=_registry_path(raw.get("render_profile_registry_path"), package_root / "render_profiles.json"),
        artifact_policy_path=_registry_path(raw.get("artifact_policy_path"), package_root / "artifact_retention.json"),
        artifact_registry_path=_path(str(raw.get("artifact_registry_path", "")), base / "artifact_registry.json"),
        runtime_log_root=_path(str(raw.get("runtime_log_root", "")), base / "runtime-logs"),
        resolve_archive_root=_path(str(raw.get("resolve_archive_root", "")), base / "resolve-archives"),
        resolve_retirement_registry_path=_path(
            str(raw.get("resolve_retirement_registry_path", "")), base / "resolve-retirements.json"
        ),
        editorial_jobs_path=_path(
            str(raw.get("editorial_jobs_path", "")), editorial_root / "editorial_jobs.json"
        ),
        editorial_journal_path=_path(
            str(raw.get("editorial_journal_path", "")), editorial_root / "editorial_journal.jsonl"
        ),
        editorial_profile_overlay_path=_path(
            str(raw.get("editorial_profile_overlay_path", "")), editorial_root / "editorial_profile_overlay.json"
        ),
        editorial_profile_proposals_path=_path(
            str(raw.get("editorial_profile_proposals_path", "")), editorial_root / "editorial_profile_proposals.json"
        ),
        carabellese_jobs_path=_path(
            str(raw.get("carabellese_jobs_path", "")), editorial_root / "carabellese_jobs.json"
        ),
        carabellese_journal_path=_path(
            str(raw.get("carabellese_journal_path", "")), editorial_root / "carabellese_journal.jsonl"
        ),
        carabellese_profile_overlay_path=_path(
            str(raw.get("carabellese_profile_overlay_path", "")),
            editorial_root / "carabellese_profile_overlay.json",
        ),
        carabellese_profile_proposals_path=_path(
            str(raw.get("carabellese_profile_proposals_path", "")),
            editorial_root / "carabellese_profile_proposals.json",
        ),
        carabellese_checkpoint_root=_path(
            str(raw.get("carabellese_checkpoint_root", "")), editorial_root / "carabellese-checkpoints"
        ),
        vertical_social_plans_path=_path(
            str(raw.get("vertical_social_plans_path", "")), editorial_root / "vertical_social_plans.json"
        ),
        vertical_social_journal_path=_path(
            str(raw.get("vertical_social_journal_path", "")), editorial_root / "vertical_social_journal.jsonl"
        ),
    )

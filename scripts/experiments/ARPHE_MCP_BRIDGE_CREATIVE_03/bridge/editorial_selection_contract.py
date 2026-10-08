from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .safety import ValidationError


WORKFLOW_ID = "ARPHE_PODCAST_REELS_CTA"
CONTRACT_KEYS = {
    "schema_version", "workflow_id", "max_candidates", "max_final_seconds",
    "marker_color", "cta_duration_seconds", "cta_media_pool_name",
    "modified_anchor_window_seconds",
}
PROFILE_KEYS = {
    "schema_version", "profile_version", "workflow_id", "aggregate_preferences",
    "sample_counts", "digest",
}
RESOLVE_MARKER_COLORS = {"Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple"}
AGGREGATE_KEYS = {
    "preferred_duration_seconds",
    "weak_opening_tags",
    "context_reduction_seconds",
    "unchanged_approval_tags",
}
TAG = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
EDITORIAL_JOB_ID = re.compile(r"^editorial_[0-9a-f]{16}$")


@dataclass(frozen=True)
class SelectionContract:
    schema_version: int
    workflow_id: str
    max_candidates: int
    max_final_seconds: float
    marker_color: str
    cta_duration_seconds: float
    cta_media_pool_name: str
    modified_anchor_window_seconds: float


@dataclass(frozen=True)
class PreferenceProfile:
    schema_version: int
    profile_version: int
    workflow_id: str
    aggregate_preferences: dict[str, object]
    sample_counts: dict[str, int]
    digest: str


def canonical_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"JSON editoriale non leggibile: {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValidationError("Il documento editoriale deve essere un oggetto JSON")
    return raw


def _exact_keys(raw: Mapping[str, object], expected: set[str], kind: str) -> None:
    missing = expected - set(raw)
    unknown = set(raw) - expected
    if missing or unknown:
        raise ValidationError(
            f"{kind}: campi mancanti={sorted(missing)}, sconosciuti={sorted(unknown)}"
        )


def _plain_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} deve essere numerico")
    result = float(value)
    if not 0 < result < float("inf"):
        raise ValidationError(f"{name} deve essere positivo e finito")
    return result


def load_selection_contract(path: Path) -> SelectionContract:
    raw = _object(path)
    _exact_keys(raw, CONTRACT_KEYS, "selection contract")
    if raw["schema_version"] != 1 or isinstance(raw["schema_version"], bool):
        raise ValidationError("Selection contract schema non supportato")
    if raw["workflow_id"] != WORKFLOW_ID:
        raise ValidationError("Selection contract limitato ad ARPHE_PODCAST_REELS_CTA")
    maximum = raw["max_candidates"]
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 20:
        raise ValidationError("max_candidates deve essere un intero tra 1 e 20")
    final_seconds = _plain_number(raw["max_final_seconds"], "max_final_seconds")
    if final_seconds != 180.0:
        raise ValidationError("max_final_seconds deve essere 180.0")
    marker_color = raw["marker_color"]
    if not isinstance(marker_color, str) or marker_color not in RESOLVE_MARKER_COLORS:
        raise ValidationError("marker_color non supportato da Resolve")
    cta = _plain_number(raw["cta_duration_seconds"], "cta_duration_seconds")
    cta_name = raw["cta_media_pool_name"]
    if not isinstance(cta_name, str) or not re.fullmatch(r"ARPHE_[A-Z0-9_]{3,80}", cta_name):
        raise ValidationError("cta_media_pool_name non valido")
    window = _plain_number(raw["modified_anchor_window_seconds"], "modified_anchor_window_seconds")
    if cta >= final_seconds or window > 600:
        raise ValidationError("Durata CTA o finestra anchor fuori limite")
    return SelectionContract(1, WORKFLOW_ID, maximum, final_seconds, marker_color, cta, cta_name, window)


def _tags(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str)
        or not TAG.fullmatch(item)
        or EDITORIAL_JOB_ID.fullmatch(item)
        for item in value
    ):
        raise ValidationError(f"{name} accetta solo tag normalizzati")
    if len(value) != len(set(value)):
        raise ValidationError(f"{name} contiene tag duplicati")
    return list(value)


def _number_pair(value: object, keys: set[str], name: str, *, ordered: bool = False) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValidationError(f"{name} deve contenere esattamente {sorted(keys)}")
    clean = {key: _plain_number(value[key], f"{name}.{key}") for key in sorted(keys)}
    if ordered and clean["min"] > clean["max"]:
        raise ValidationError(f"{name}.min non può superare max")
    return clean


def _validate_aggregates(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError("aggregate_preferences deve essere un oggetto")
    unknown = set(value) - AGGREGATE_KEYS
    if unknown:
        raise ValidationError(f"Preferenze aggregate sconosciute: {sorted(unknown)}")
    clean: dict[str, object] = {}
    for key, raw in value.items():
        if key == "preferred_duration_seconds":
            pair = _number_pair(raw, {"min", "max"}, key, ordered=True)
            if pair["max"] > 180.0:
                raise ValidationError("La durata preferita non può superare 180 secondi")
            clean[key] = pair
        elif key == "context_reduction_seconds":
            clean[key] = _number_pair(raw, {"median_start", "median_end"}, key)
        else:
            clean[key] = _tags(raw, key)
    return clean


def load_preference_profile(path: Path) -> PreferenceProfile:
    raw = _object(path)
    _exact_keys(raw, PROFILE_KEYS, "preference profile")
    if raw["schema_version"] != 1 or isinstance(raw["schema_version"], bool):
        raise ValidationError("Preference profile schema non supportato")
    version = raw["profile_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValidationError("profile_version deve essere un intero positivo")
    if raw["workflow_id"] != WORKFLOW_ID:
        raise ValidationError("Preference profile limitato ad ARPHE_PODCAST_REELS_CTA")
    digest = raw["digest"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValidationError("Digest profilo non valido")
    unsigned = {key: value for key, value in raw.items() if key != "digest"}
    if canonical_digest(unsigned) != digest:
        raise ValidationError("Digest profilo non corrispondente al contenuto")
    aggregates = _validate_aggregates(raw["aggregate_preferences"])
    counts = raw["sample_counts"]
    if not isinstance(counts, dict) or set(counts) != set(aggregates):
        raise ValidationError("sample_counts deve corrispondere alle preferenze aggregate")
    clean_counts: dict[str, int] = {}
    for key, value in counts.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValidationError("Ogni sample count deve essere un intero positivo")
        clean_counts[key] = value
    return PreferenceProfile(1, version, WORKFLOW_ID, aggregates, clean_counts, digest)

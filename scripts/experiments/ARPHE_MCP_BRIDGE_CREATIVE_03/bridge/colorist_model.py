from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .safety import ValidationError


PRESET_SCHEMA = "ARPHE_COLORIST_PRESETS_V1"
PRESET_NAME = re.compile(r"^ARPHE_[A-Z0-9_]{2,48}$")
ADJUSTMENT_LIMITS = {
    "temperature": (-1.0, 1.0),
    "tint": (-1.0, 1.0),
    "exposure_stops": (-2.0, 2.0),
    "contrast": (-1.0, 1.0),
    "saturation": (0.0, 2.0),
}
NEUTRAL = {
    "temperature": 0.0,
    "tint": 0.0,
    "exposure_stops": 0.0,
    "contrast": 0.0,
    "saturation": 1.0,
}
OBSERVATION_KEYS = {
    "source", "sample_frames", "neutral_rgb", "luma_percentiles", "mean_saturation",
}
OBSERVATION_SOURCES = {"SCOPES", "REGISTERED_STILL"}


def _number(value: object, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{name} non valido")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} deve essere numerico") from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValidationError(f"{name} deve essere tra {minimum} e {maximum}")
    return result


def _validate_adjustments(raw: Mapping[str, object], *, allow_missing: bool = True) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise ValidationError("adjustments deve essere un oggetto")
    unknown = set(raw) - set(ADJUSTMENT_LIMITS)
    if unknown:
        raise ValidationError(f"Correzioni sconosciute: {sorted(unknown)}")
    values: dict[str, float] = {}
    for name, (minimum, maximum) in ADJUSTMENT_LIMITS.items():
        if name not in raw:
            if allow_missing:
                values[name] = NEUTRAL[name]
                continue
            raise ValidationError(f"Preset incompleto: {name}")
        values[name] = _number(raw[name], name, minimum, maximum)
    return values


def load_colorist_presets(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Registry preset Colorist non leggibile: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "presets", "drx_presets"}:
        raise ValidationError("Registry preset Colorist malformato")
    if payload["schema"] != PRESET_SCHEMA:
        raise ValidationError("Schema preset Colorist non supportato")
    if not isinstance(payload["presets"], dict) or not payload["presets"]:
        raise ValidationError("Almeno un preset Colorist richiesto")
    if not isinstance(payload["drx_presets"], dict):
        raise ValidationError("drx_presets deve essere un oggetto")
    presets: dict[str, dict[str, float]] = {}
    for name, raw in payload["presets"].items():
        if not isinstance(name, str) or not PRESET_NAME.fullmatch(name):
            raise ValidationError("Nome preset Colorist non valido")
        presets[name] = _validate_adjustments(raw, allow_missing=False)
    drx_presets: dict[str, str] = {}
    for name, relative in payload["drx_presets"].items():
        if not isinstance(name, str) or not PRESET_NAME.fullmatch(name):
            raise ValidationError("Nome preset DRX non valido")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValidationError("Percorso preset DRX deve essere relativo e confinato")
        if Path(relative).suffix.lower() != ".drx":
            raise ValidationError("Preset DRX deve usare estensione .drx")
        drx_presets[name] = relative
    return {"schema": PRESET_SCHEMA, "presets": presets, "drx_presets": drx_presets}


def build_cdl(adjustments: Mapping[str, object], preset_name: str,
              presets: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    if preset_name not in presets:
        raise ValidationError(f"Preset Colorist non consentito: {preset_name}")
    base = _validate_adjustments(presets[preset_name], allow_missing=False)
    requested = _validate_adjustments(adjustments)
    combined = {
        "temperature": _number(base["temperature"] + requested["temperature"], "temperature", -1.0, 1.0),
        "tint": _number(base["tint"] + requested["tint"], "tint", -1.0, 1.0),
        "exposure_stops": _number(base["exposure_stops"] + requested["exposure_stops"], "exposure_stops", -2.0, 2.0),
        "contrast": _number(base["contrast"] + requested["contrast"], "contrast", -1.0, 1.0),
        "saturation": _number(base["saturation"] * requested["saturation"], "saturation", 0.0, 2.0),
    }

    exposure = 2.0 ** combined["exposure_stops"]
    contrast_gain = 1.0 + combined["contrast"] * 0.25
    temperature = combined["temperature"]
    tint = combined["tint"]
    tint_rb = 1.0 + tint * 0.04
    slope = (
        exposure * contrast_gain * (1.0 + temperature * 0.10) * tint_rb,
        exposure * contrast_gain * (1.0 - tint * 0.08),
        exposure * contrast_gain * (1.0 - temperature * 0.10) * tint_rb,
    )
    offset_value = -0.125 * combined["contrast"]
    return {
        "NodeIndex": 1,
        "Slope": " ".join(f"{value:.6f}" for value in slope),
        "Offset": " ".join(f"{offset_value:.6f}" for _ in range(3)),
        "Power": "1.000000 1.000000 1.000000",
        "Saturation": f"{combined['saturation']:.6f}",
    }


def _normalized_triplet(value: object, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValidationError(f"{name} deve contenere tre valori")
    return [_number(item, name, 0.0, 1.0) for item in value]


def _normalize_observation(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping) or set(raw) - OBSERVATION_KEYS:
        raise ValidationError("Osservazione tecnica Colorist malformata")
    if raw.get("source") not in OBSERVATION_SOURCES:
        raise ValidationError("Sorgente osservazione Colorist non consentita")
    frames = raw.get("sample_frames")
    if (not isinstance(frames, (list, tuple)) or not 1 <= len(frames) <= 3
            or any(isinstance(frame, bool) or not isinstance(frame, int) or frame < 0
                   for frame in frames)):
        raise ValidationError("sample_frames Colorist non validi")
    normalized: dict[str, object] = {
        "source": str(raw["source"]),
        "sample_frames": sorted(set(frames)),
    }
    if "neutral_rgb" in raw:
        normalized["neutral_rgb"] = _normalized_triplet(raw["neutral_rgb"], "neutral_rgb")
    if "luma_percentiles" in raw:
        percentiles = _normalized_triplet(raw["luma_percentiles"], "luma_percentiles")
        if not percentiles[0] < percentiles[1] < percentiles[2]:
            raise ValidationError("luma_percentiles deve rispettare p10 < p50 < p90")
        normalized["luma_percentiles"] = percentiles
    if "mean_saturation" in raw:
        normalized["mean_saturation"] = _number(
            raw["mean_saturation"], "mean_saturation", 0.0, 1.0,
        )
    if set(normalized) == {"source", "sample_frames"}:
        raise ValidationError("Osservazione Colorist priva di misure")
    return normalized


def validate_normalized_adjustments(raw: Mapping[str, object]) -> None:
    normalized = _validate_adjustments(raw, allow_missing=False)
    if dict(raw) != normalized:
        raise ValidationError("Correzioni Colorist non canoniche")


def validate_normalized_observation(raw: Mapping[str, object]) -> None:
    if dict(raw) != _normalize_observation(raw):
        raise ValidationError("Osservazione Colorist non canonica")


def validate_cdl(cdl: Mapping[str, object]) -> None:
    required = {"NodeIndex", "Slope", "Offset", "Power", "Saturation"}
    if not isinstance(cdl, Mapping) or set(cdl) != required:
        raise ValidationError("CDL Colorist malformato")
    node = cdl["NodeIndex"]
    if isinstance(node, bool) or not isinstance(node, int) or node < 1:
        raise ValidationError("NodeIndex CDL non valido")

    for name in ("Slope", "Offset", "Power"):
        raw = cdl[name]
        if not isinstance(raw, str) or len(raw.split()) != 3:
            raise ValidationError(f"{name} CDL deve contenere tre valori")
        try:
            values = [float(value) for value in raw.split()]
        except ValueError:
            raise ValidationError(f"{name} CDL non numerico") from None
        if not all(math.isfinite(value) for value in values):
            raise ValidationError(f"{name} CDL non finito")
        if name in {"Slope", "Power"} and not all(value > 0.0 for value in values):
            raise ValidationError(f"{name} CDL deve essere positivo")

    saturation = cdl["Saturation"]
    if not isinstance(saturation, str):
        raise ValidationError("Saturation CDL non valida")
    _number(saturation, "Saturation CDL", 0.0, 2.0)


def build_clip_corrections(
    clip_ids: tuple[str, ...] | list[str],
    adjustments: Mapping[str, object],
    adjustments_by_clip: Mapping[str, Mapping[str, object]] | None,
    observations_by_clip: Mapping[str, Mapping[str, object]] | None,
    preset_name: str,
    presets: Mapping[str, Mapping[str, object]],
) -> tuple[str, dict[str, dict[str, float]], dict[str, dict[str, object]],
           dict[str, dict[str, object]]]:
    clips = tuple(clip_ids)
    if (not clips or len(set(clips)) != len(clips)
            or any(not isinstance(clip_id, str) or not clip_id for clip_id in clips)):
        raise ValidationError("clip_ids Colorist vuoti, duplicati o non validi")
    targets = set(clips)
    if adjustments_by_clip is None:
        if observations_by_clip not in (None, {}):
            raise ValidationError("Le osservazioni per clip richiedono correzioni per clip")
        normalized = _validate_adjustments(adjustments)
        by_clip = {clip_id: dict(normalized) for clip_id in clips}
        cdls = {clip_id: build_cdl(normalized, preset_name, presets) for clip_id in clips}
        return "UNIFORM_MANUAL", by_clip, {}, cdls

    if adjustments:
        raise ValidationError("La correzione globale deve essere vuota con adjustments_by_clip")
    if (not isinstance(adjustments_by_clip, Mapping)
            or set(adjustments_by_clip) != targets):
        raise ValidationError("adjustments_by_clip deve coprire esattamente i clip selezionati")
    if (not isinstance(observations_by_clip, Mapping)
            or set(observations_by_clip) != targets):
        raise ValidationError("observations_by_clip deve coprire esattamente i clip selezionati")

    by_clip: dict[str, dict[str, float]] = {}
    observations: dict[str, dict[str, object]] = {}
    cdls: dict[str, dict[str, object]] = {}
    for clip_id in clips:
        raw_adjustments = adjustments_by_clip[clip_id]
        normalized = _validate_adjustments(raw_adjustments)
        by_clip[clip_id] = normalized
        observations[clip_id] = _normalize_observation(observations_by_clip[clip_id])
        cdls[clip_id] = build_cdl(normalized, preset_name, presets)
    return "PER_CLIP_MEASURED", by_clip, observations, cdls


def cdl_digest(cdl: Mapping[str, object]) -> str:
    validate_cdl(cdl)
    canonical = json.dumps(cdl, ensure_ascii=True, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def plan_fingerprint(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise ValidationError("Payload piano Colorist non valido")
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


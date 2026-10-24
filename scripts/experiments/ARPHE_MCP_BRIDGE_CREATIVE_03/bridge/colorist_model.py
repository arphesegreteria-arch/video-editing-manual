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


def plan_fingerprint(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise ValidationError("Payload piano Colorist non valido")
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


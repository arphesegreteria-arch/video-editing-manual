from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .safety import ValidationError


WORKFLOW_ID = "CARABELLESE_YOUTUBE_CLEANUP"
CONTRACT_KEYS = {
    "schema_version", "workflow_id", "version", "resolution", "frame_rate_mode",
    "retain_below_seconds", "contextual_through_seconds", "residual_min_seconds",
    "residual_max_seconds", "protected_silence_handle_seconds", "cue_review_required",
    "transcript_schema", "marker_color",
}
PREFERENCE_KEYS = {
    "schema_version", "workflow_id", "version", "residual_pause_seconds",
    "minimum_learning_samples",
}


@dataclass(frozen=True)
class CarabelleseContract:
    schema_version: int
    workflow_id: str
    version: int
    resolution: tuple[int, int]
    frame_rate_mode: str
    retain_below_seconds: float
    contextual_through_seconds: float
    residual_min_seconds: float
    residual_max_seconds: float
    protected_silence_handle_seconds: float
    cue_review_required: bool
    transcript_schema: str
    marker_color: str


@dataclass(frozen=True)
class CarabellesePreferences:
    schema_version: int
    workflow_id: str
    version: int
    residual_pause_seconds: float
    minimum_learning_samples: int


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Registry Carabellese non leggibile: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("Registry Carabellese deve essere un oggetto")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise ValidationError(f"{label}: campi sconosciuti: {sorted(unknown)}")
    if missing:
        raise ValidationError(f"{label}: campi mancanti: {sorted(missing)}")


def load_carabellese_contract(path: Path) -> CarabelleseContract:
    raw = _object(path)
    _exact_keys(raw, CONTRACT_KEYS, "Contratto Carabellese")
    try:
        resolution = tuple(int(value) for value in raw["resolution"])
        contract = CarabelleseContract(
            schema_version=int(raw["schema_version"]), workflow_id=str(raw["workflow_id"]),
            version=int(raw["version"]), resolution=resolution,  # type: ignore[arg-type]
            frame_rate_mode=str(raw["frame_rate_mode"]),
            retain_below_seconds=float(raw["retain_below_seconds"]),
            contextual_through_seconds=float(raw["contextual_through_seconds"]),
            residual_min_seconds=float(raw["residual_min_seconds"]),
            residual_max_seconds=float(raw["residual_max_seconds"]),
            protected_silence_handle_seconds=float(raw["protected_silence_handle_seconds"]),
            cue_review_required=raw["cue_review_required"],
            transcript_schema=str(raw["transcript_schema"]), marker_color=str(raw["marker_color"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Contratto Carabellese malformato: {exc}") from exc
    if (contract.schema_version != 1 or contract.workflow_id != WORKFLOW_ID
            or contract.version < 1 or contract.resolution != (1920, 1080)
            or contract.frame_rate_mode != "source"
            or not 0 < contract.retain_below_seconds <= contract.contextual_through_seconds
            or not 0 < contract.residual_min_seconds <= contract.residual_max_seconds
            or contract.residual_max_seconds > contract.contextual_through_seconds
            or not 0 <= contract.protected_silence_handle_seconds < contract.residual_min_seconds
            or contract.cue_review_required is not True
            or contract.transcript_schema != "ARPHE_TRANSCRIPT_V1"
            or not contract.marker_color.strip()):
        raise ValidationError("Contratto Carabellese non supportato")
    return contract


def load_carabellese_preferences(path: Path) -> CarabellesePreferences:
    raw = _object(path)
    _exact_keys(raw, PREFERENCE_KEYS, "Preferenze Carabellese")
    try:
        preferences = CarabellesePreferences(
            schema_version=int(raw["schema_version"]), workflow_id=str(raw["workflow_id"]),
            version=int(raw["version"]), residual_pause_seconds=float(raw["residual_pause_seconds"]),
            minimum_learning_samples=int(raw["minimum_learning_samples"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Preferenze Carabellese malformate: {exc}") from exc
    if (preferences.schema_version != 1 or preferences.workflow_id != WORKFLOW_ID
            or preferences.version < 1 or preferences.residual_pause_seconds <= 0
            or preferences.minimum_learning_samples < 1):
        raise ValidationError("Preferenze Carabellese con workflow_id o valori non supportati")
    return preferences


def carabellese_contract_fingerprint(contract: CarabelleseContract) -> str:
    encoded = json.dumps(asdict(contract), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .safety import ValidationError


@dataclass(frozen=True)
class BrandProfile:
    profile_id: str
    kit_status: str
    allowed_operations: tuple[str, ...]
    allowed_asset_classes: tuple[str, ...]

    def allows_operation(self, operation: str) -> bool:
        return operation in self.allowed_operations and self.kit_status == "READY" if operation in {"GRAPHIC", "CARD"} else operation in self.allowed_operations


@dataclass(frozen=True)
class BrandedLongformContract:
    schema_version: int
    workflow_id: str
    version: int
    source_modes: tuple[str, ...]
    semantic_classes: tuple[str, ...]
    profiles: dict[str, BrandProfile]

    def profile(self, profile_id: str) -> BrandProfile:
        try:
            return self.profiles[profile_id]
        except KeyError as exc:
            raise ValidationError(f"Profilo longform sconosciuto: {profile_id}") from exc


def load_branded_longform_contract(path: Path) -> BrandedLongformContract:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Contratto branded longform non leggibile: {exc}") from exc
    keys = {"schema_version", "workflow_id", "version", "source_modes", "semantic_classes", "profiles"}
    if not isinstance(raw, dict) or set(raw) != keys:
        unknown = set(raw) - keys if isinstance(raw, dict) else set()
        raise ValidationError(f"Contratto branded longform: campi sconosciuti o mancanti: {sorted(unknown)}")
    profiles: dict[str, BrandProfile] = {}
    for value in raw["profiles"]:
        required = {"profile_id", "kit_status", "allowed_operations", "allowed_asset_classes"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValidationError("Profilo branded longform non valido")
        profile = BrandProfile(str(value["profile_id"]), str(value["kit_status"]), tuple(map(str, value["allowed_operations"])), tuple(map(str, value["allowed_asset_classes"])))
        if profile.profile_id in profiles:
            raise ValidationError(f"Profilo duplicato: {profile.profile_id}")
        if profile.kit_status not in {"READY", "PENDING"}:
            raise ValidationError("kit_status non supportato")
        profiles[profile.profile_id] = profile
    contract = BrandedLongformContract(int(raw["schema_version"]), str(raw["workflow_id"]), int(raw["version"]), tuple(map(str, raw["source_modes"])), tuple(map(str, raw["semantic_classes"])), profiles)
    if contract.schema_version != 1 or contract.workflow_id != "BRANDED_LONGFORM_EDITORIAL" or set(contract.profiles) != {"ARPHE_LONGFORM_EDITORIAL", "CARABELLESE_LONGFORM_EDITORIAL"}:
        raise ValidationError("Contratto branded longform non supportato")
    return contract


def branded_longform_fingerprint(contract: BrandedLongformContract, profile: BrandProfile) -> str:
    payload = {"contract": {**asdict(contract), "profiles": {key: asdict(value) for key, value in contract.profiles.items()}}, "profile": asdict(profile)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

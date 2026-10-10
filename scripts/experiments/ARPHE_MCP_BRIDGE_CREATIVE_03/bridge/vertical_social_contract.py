from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .safety import ValidationError


_ACTION_KEYS = {"type", "phase", "required_capability", "capability_status", "executable"}
_CONTRACT_KEYS = {"schema_version", "workflow_id", "version", "phases", "actions"}
_ACTION_STATUSES = {"VALIDATED", "PARTIAL", "EXPERIMENTAL", "UNAVAILABLE"}


@dataclass(frozen=True)
class VerticalSocialActionSpec:
    action_type: str
    phase: str
    required_capability: str
    capability_status: str
    executable: bool


@dataclass(frozen=True)
class VerticalSocialContract:
    workflow_id: str
    version: int
    phases: tuple[str, ...]
    actions: dict[str, VerticalSocialActionSpec]

    def action(self, action_type: str) -> VerticalSocialActionSpec:
        try:
            return self.actions[action_type]
        except KeyError as exc:
            raise ValidationError(f"Azione sconosciuta: {action_type}") from exc


def _strict_keys(value: dict[str, Any], allowed: set[str], kind: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValidationError(f"{kind}: campi sconosciuti: {sorted(unknown)}")


def load_vertical_social_contract(path: Path) -> VerticalSocialContract:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Contratto Vertical Social non leggibile: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValidationError("Contratto Vertical Social non valido")
    _strict_keys(raw, _CONTRACT_KEYS, "contratto")
    if raw.get("schema_version") != 1 or raw.get("workflow_id") != "ARPHE_VERTICAL_SOCIAL":
        raise ValidationError("Schema o workflow_id del contratto non supportato")
    phases = tuple(raw.get("phases", ()))
    if phases != ("ANALYSE", "PROPOSE", "PROVISIONAL_EDIT", "PICTURE_LOCK", "POST_LOCK", "REVIEW"):
        raise ValidationError("Fasi Vertical Social non valide")
    loaded: dict[str, VerticalSocialActionSpec] = {}
    for item in raw.get("actions", ()):
        if not isinstance(item, dict):
            raise ValidationError("Azione Vertical Social non valida")
        _strict_keys(item, _ACTION_KEYS, "azione")
        if set(item) != _ACTION_KEYS:
            raise ValidationError("Azione Vertical Social incompleta")
        action_type = str(item["type"])
        if action_type in loaded:
            raise ValidationError(f"Azione duplicata: {action_type}")
        phase = str(item["phase"])
        status = str(item["capability_status"])
        if phase not in phases or status not in _ACTION_STATUSES:
            raise ValidationError("Fase o stato capability non valido")
        loaded[action_type] = VerticalSocialActionSpec(
            action_type=action_type,
            phase=phase,
            required_capability=str(item["required_capability"]),
            capability_status=status,
            executable=bool(item["executable"]),
        )
    if not loaded:
        raise ValidationError("Contratto senza azioni")
    return VerticalSocialContract("ARPHE_VERTICAL_SOCIAL", int(raw["version"]), phases, loaded)


def validate_action_request(contract: VerticalSocialContract, action: dict[str, Any],
                            picture_locked: bool, known_action_ids: set[str] | None = None
                            ) -> VerticalSocialActionSpec:
    if not isinstance(action, dict):
        raise ValidationError("Azione richiesta non valida")
    required = {"action_id", "type", "phase"}
    missing = required - set(action)
    if missing:
        raise ValidationError(f"Azione richiesta incompleta: {sorted(missing)}")
    spec = contract.action(str(action["type"]))
    if str(action["phase"]) != spec.phase:
        raise ValidationError(f"Fase non consentita per {spec.action_type}")
    dependencies = action.get("depends_on", [])
    if not isinstance(dependencies, list):
        raise ValidationError("dipendenza non valida")
    known = known_action_ids or set()
    if any(not isinstance(value, str) or value not in known for value in dependencies):
        raise ValidationError("dipendenza non risolta")
    if spec.action_type == "CAPTIONS" and not picture_locked:
        raise ValidationError("CAPTIONS richiede picture lock")
    if spec.action_type == "CAPTIONS" and spec.capability_status != "VALIDATED":
        raise ValidationError("CAPTIONS capability non validata")
    return spec


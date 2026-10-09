from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from .safety import ValidationError


_ACTION_STATES = {"PROPOSED", "APPROVED", "APPLIED", "VERIFIED", "READY_FOR_REVIEW",
                  "BLOCKED", "REJECTED", "SUPERSEDED"}
_TRANSITIONS = {
    "PROPOSED": {"APPROVED", "REJECTED", "SUPERSEDED"},
    "APPROVED": {"APPLIED", "VERIFIED", "BLOCKED", "REJECTED", "SUPERSEDED"},
    "APPLIED": {"VERIFIED", "BLOCKED", "SUPERSEDED"},
    "VERIFIED": {"READY_FOR_REVIEW", "SUPERSEDED"},
    "BLOCKED": {"APPROVED", "SUPERSEDED"},
    "READY_FOR_REVIEW": set(),
    "REJECTED": set(),
    "SUPERSEDED": set(),
}


@dataclass(frozen=True)
class VerticalSocialAction:
    action_id: str
    action_type: str
    phase: str
    state: str
    evidence: dict[str, Any]
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"action_id": self.action_id, "type": self.action_type, "phase": self.phase,
                "state": self.state, "evidence": self.evidence, **self.parameters}


@dataclass(frozen=True)
class VerticalSocialPlan:
    plan_id: str
    version: int
    workstation_id: str
    target: dict[str, Any]
    actions: tuple[VerticalSocialAction, ...]

    def action(self, action_id: str) -> VerticalSocialAction:
        for action in self.actions:
            if action.action_id == action_id:
                return action
        raise ValidationError(f"Azione piano sconosciuta: {action_id}")

    def to_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "version": self.version, "workstation_id": self.workstation_id,
                "target": self.target, "actions": [action.to_dict() for action in self.actions]}


def plan_fingerprint(plan: VerticalSocialPlan) -> str:
    payload = {
        "plan_id": plan.plan_id, "version": plan.version,
        "workstation_id": plan.workstation_id, "target": plan.target,
        "actions": [
            {"action_id": action.action_id, "type": action.action_type, "phase": action.phase,
             **action.parameters}
            for action in plan.actions
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_vertical_social_plan(*, workstation_id: str, target: dict[str, Any],
                             actions: list[dict[str, Any]], plan_id: str | None = None,
                             version: int = 1) -> VerticalSocialPlan:
    if not workstation_id.startswith("PC_") or not isinstance(target, dict):
        raise ValidationError("Piano Vertical Social non valido")
    created: list[VerticalSocialAction] = []
    seen: set[str] = set()
    for raw in actions:
        action_id = str(raw.get("action_id", ""))
        if not action_id or action_id in seen:
            raise ValidationError("action_id mancante o duplicato")
        seen.add(action_id)
        parameters = {
            key: value for key, value in raw.items()
            if key not in {"action_id", "type", "phase", "state", "evidence"}
        }
        created.append(VerticalSocialAction(
            action_id=action_id, action_type=str(raw.get("type", "")),
            phase=str(raw.get("phase", "")), state=str(raw.get("state", "APPROVED")),
            evidence=dict(raw.get("evidence", {})),
            parameters=parameters,
        ))
    return VerticalSocialPlan(plan_id or f"vertical_{uuid4().hex}", int(version), workstation_id,
                              dict(target), tuple(created))


class VerticalSocialPlanStore:
    def __init__(self, path: Path, workstation_id: str):
        self.path = path
        self.workstation_id = workstation_id
        if path.exists():
            owner = self._read()["workstation_id"]
            if owner != workstation_id:
                raise ValidationError("Registro Vertical Social appartiene a un'altra workstation")

    def _read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Registro Vertical Social non leggibile: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("workstation_id") != self.workstation_id:
            raise ValidationError("Registro Vertical Social workstation non valida")
        return raw

    def _write(self, plans: dict[str, VerticalSocialPlan]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {"workstation_id": self.workstation_id,
               "plans": {plan_id: plan.to_dict() for plan_id, plan in plans.items()}}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(raw, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _decode(raw: dict[str, Any]) -> VerticalSocialPlan:
        return new_vertical_social_plan(
            workstation_id=str(raw["workstation_id"]), target=dict(raw["target"]),
            actions=[dict(action) for action in raw["actions"]], plan_id=str(raw["plan_id"]),
            version=int(raw["version"]),
        )

    def _plans(self) -> dict[str, VerticalSocialPlan]:
        if not self.path.exists():
            return {}
        return {plan_id: self._decode(value) for plan_id, value in self._read().get("plans", {}).items()}

    def create(self, plan: VerticalSocialPlan) -> VerticalSocialPlan:
        if plan.workstation_id != self.workstation_id:
            raise ValidationError("Piano di un'altra workstation")
        plans = self._plans()
        existing = plans.get(plan.plan_id)
        if existing is not None:
            if plan_fingerprint(existing) != plan_fingerprint(plan):
                raise ValidationError("plan_id esistente con fingerprint diversa")
            return existing
        plans[plan.plan_id] = plan
        self._write(plans)
        return plan

    def get(self, plan_id: str) -> VerticalSocialPlan:
        try:
            return self._plans()[plan_id]
        except KeyError as exc:
            raise ValidationError("Piano Vertical Social sconosciuto") from exc

    def replace(self, plan: VerticalSocialPlan) -> VerticalSocialPlan:
        plans = self._plans()
        if plan.plan_id not in plans:
            raise ValidationError("Piano Vertical Social sconosciuto")
        plans[plan.plan_id] = plan
        self._write(plans)
        return plan


def transition_action(store: VerticalSocialPlanStore, plan_id: str, action_id: str,
                      expected_state: str, next_state: str, evidence: dict[str, Any]
                      ) -> VerticalSocialPlan:
    plan = store.get(plan_id)
    action = plan.action(action_id)
    if action.state == next_state:
        return plan
    if action.state != expected_state or next_state not in _TRANSITIONS.get(action.state, set()):
        raise ValidationError(f"Transizione azione non consentita: {action.state} -> {next_state}")
    updated = replace(action, state=next_state, evidence=dict(evidence))
    return store.replace(replace(
        plan, actions=tuple(updated if item.action_id == action_id else item for item in plan.actions)
    ))


def next_safe_action(plan: VerticalSocialPlan) -> VerticalSocialAction | None:
    for action in plan.actions:
        if action.state == "BLOCKED":
            return action
    return next((action for action in plan.actions if action.state == "APPROVED"), None)

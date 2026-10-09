from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .safety import ValidationError
from .vertical_social_contract import load_vertical_social_contract, validate_action_request
from .vertical_social_jobs import VerticalSocialPlanStore, new_vertical_social_plan, next_safe_action, plan_fingerprint, transition_action


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "vertical_social_contract.json"


@dataclass(frozen=True)
class VerticalSocialWorkflowPlan:
    plan_id: str
    fingerprint: str
    state: str
    picture_locked: bool


def _meta_path(path: Path) -> Path:
    return path.with_name(path.stem + "_workflow.json")


def _load_meta(path: Path) -> dict[str, dict[str, Any]]:
    selected = _meta_path(path)
    if not selected.exists():
        return {}
    return json.loads(selected.read_text(encoding="utf-8"))


def _save_meta(path: Path, values: dict[str, dict[str, Any]]) -> None:
    selected = _meta_path(path)
    selected.write_text(json.dumps(values, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _wrapped(path: Path, plan_id: str) -> VerticalSocialWorkflowPlan:
    raw = _load_meta(path).get(plan_id)
    if not raw:
        raise ValidationError("Piano Vertical Social sconosciuto")
    return VerticalSocialWorkflowPlan(plan_id, raw["fingerprint"], raw["state"], bool(raw["picture_locked"]))


def prepare_vertical_social_plan(path: Path, workstation_id: str, target: dict[str, Any],
                                 actions: list[dict[str, Any]]) -> VerticalSocialWorkflowPlan:
    contract = load_vertical_social_contract(CONTRACT_PATH)
    known: set[str] = set()
    for action in actions:
        if str(action.get("type")) == "CAPTIONS":
            spec = contract.action("CAPTIONS")
            if str(action.get("phase")) != spec.phase:
                raise ValidationError("Fase non consentita per CAPTIONS")
        else:
            validate_action_request(contract, action, False, known)
        known.add(str(action["action_id"]))
    store = VerticalSocialPlanStore(path, workstation_id)
    plan = store.create(new_vertical_social_plan(workstation_id=workstation_id, target=target, actions=actions))
    meta = _load_meta(path)
    meta[plan.plan_id] = {"fingerprint": plan_fingerprint(plan), "state": "PROPOSED", "picture_locked": False}
    _save_meta(path, meta)
    return _wrapped(path, plan.plan_id)


def approve_vertical_social_plan(path: Path, workstation_id: str, plan_id: str,
                                 fingerprint: str) -> VerticalSocialWorkflowPlan:
    store = VerticalSocialPlanStore(path, workstation_id)
    plan = store.get(plan_id)
    wrapped = _wrapped(path, plan_id)
    if wrapped.fingerprint != fingerprint or plan_fingerprint(plan) != fingerprint:
        raise ValidationError("fingerprint piano non corrispondente")
    meta = _load_meta(path)
    meta[plan_id]["state"] = "APPROVED"
    _save_meta(path, meta)
    return _wrapped(path, plan_id)


def approved_vertical_social_plan(path: Path, workstation_id: str, plan_id: str,
                                  fingerprint: str):
    """Load only the exact plan the editor has explicitly approved for execution."""
    plan = VerticalSocialPlanStore(path, workstation_id).get(plan_id)
    wrapped = _wrapped(path, plan_id)
    if wrapped.state != "APPROVED":
        raise ValidationError("Piano Vertical Social non approvato")
    if wrapped.fingerprint != fingerprint or plan_fingerprint(plan) != fingerprint:
        raise ValidationError("fingerprint piano non corrispondente")
    return plan


def record_vertical_social_cut_execution(path: Path, workstation_id: str, plan_id: str,
                                         fingerprint: str, provisional_timeline: str,
                                         final_frames: int):
    """Persist only CUT evidence after the provisional timeline has passed its read-back."""
    plan = approved_vertical_social_plan(path, workstation_id, plan_id, fingerprint)
    if not provisional_timeline.startswith("__ARPHE_VERTICAL_") or final_frames <= 0:
        raise ValidationError("Evidenza CUT provvisoria non valida")
    store = VerticalSocialPlanStore(path, workstation_id)
    evidence = {"provisional_timeline": provisional_timeline, "final_frames": final_frames}
    for action in plan.actions:
        if action.action_type != "CUT":
            continue
        current = store.get(plan_id).action(action.action_id)
        if current.state == "APPROVED":
            transition_action(store, plan_id, action.action_id, "APPROVED", "APPLIED", evidence)
            current = store.get(plan_id).action(action.action_id)
        if current.state == "APPLIED":
            transition_action(store, plan_id, action.action_id, "APPLIED", "VERIFIED", evidence)
        elif current.state != "VERIFIED":
            raise ValidationError(f"CUT non eseguibile nello stato {current.state}")
    return store.get(plan_id)


def mark_vertical_social_picture_lock(path: Path, workstation_id: str,
                                      plan_id: str) -> VerticalSocialWorkflowPlan:
    VerticalSocialPlanStore(path, workstation_id).get(plan_id)
    wrapped = _wrapped(path, plan_id)
    if wrapped.state != "APPROVED":
        raise ValidationError("Picture lock richiede piano approvato")
    meta = _load_meta(path)
    meta[plan_id]["picture_locked"] = True
    _save_meta(path, meta)
    return _wrapped(path, plan_id)


def advance_vertical_social_action(path: Path, workstation_id: str, plan_id: str,
                                   action_id: str, next_state: str, evidence: dict[str, Any]):
    store = VerticalSocialPlanStore(path, workstation_id)
    wrapped = _wrapped(path, plan_id)
    if wrapped.state != "APPROVED":
        raise ValidationError("Piano non approvato")
    action = store.get(plan_id).action(action_id)
    spec = validate_action_request(
        load_vertical_social_contract(CONTRACT_PATH),
        {"action_id": action.action_id, "type": action.action_type, "phase": action.phase},
        wrapped.picture_locked,
    )
    if not spec.executable and action.action_type == "CAPTIONS":
        raise ValidationError("CAPTIONS capability non validata")
    return transition_action(store, plan_id, action_id, action.state, next_state, evidence)


def inspect_vertical_social_plan(path: Path, workstation_id: str, plan_id: str) -> dict[str, Any]:
    plan = VerticalSocialPlanStore(path, workstation_id).get(plan_id)
    wrapped = _wrapped(path, plan_id)
    next_action = next_safe_action(plan)
    return {"plan_id": plan_id, "state": wrapped.state, "picture_locked": wrapped.picture_locked,
            "next_action": None if next_action is None else next_action.action_id,
            "actions": [action.to_dict() for action in plan.actions]}


def compact_vertical_social_card(plan: VerticalSocialWorkflowPlan) -> dict[str, Any]:
    return {"card_count": 1, "plan_id": plan.plan_id, "state": plan.state,
            "picture_locked": plan.picture_locked}

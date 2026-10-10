from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .safety import ValidationError
from .vertical_social_contract import load_vertical_social_contract, validate_action_request
from .vertical_social_broll import validate_generated_broll, validate_provided_broll
from .vertical_social_graphics import approved_graphic_actions
from .vertical_social_reframe import validate_reframe_action
from .vertical_social_qc import final_vertical_social_check
from .vertical_social_music import validate_music_duck
from .vertical_social_captions import validate_caption_action
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
    total_frames = target.get("total_frames")
    for action in actions:
        action_type = str(action.get("type"))
        if action_type in {"REFRAME", "B_ROLL_PROVIDED", "GRAPHIC", "CTA", "MUSIC_DUCK"}:
            if not isinstance(total_frames, int) or total_frames <= 0:
                raise ValidationError(f"{action_type} richiede total_frames esplicito nel target")
        if action_type == "REFRAME":
            validate_reframe_action(action, total_frames)
        elif action_type == "B_ROLL_PROVIDED":
            validate_provided_broll(action, total_frames)
        elif action_type == "B_ROLL_GENERATED":
            validate_generated_broll(action)
        elif action_type in {"GRAPHIC", "CTA"}:
            approved_graphic_actions({"actions": [action]}, total_frames)
        elif action_type == "MUSIC_DUCK":
            validate_music_duck(action, total_frames)
        if action_type == "CAPTIONS":
            spec = contract.action("CAPTIONS")
            if str(action.get("phase")) != spec.phase:
                raise ValidationError("Fase non consentita per CAPTIONS")
            if not isinstance(total_frames, int) or total_frames <= 0:
                raise ValidationError("CAPTIONS richiede total_frames esplicito nel target")
            caption_plan = validate_caption_action(
                action, total_frames, allow_picture_lock_placeholder=True)
            if (caption_plan["locked_edit_fingerprint"] != "AT_PICTURE_LOCK"
                    and caption_plan["locked_edit_fingerprint"] != str(
                        target.get("locked_edit_fingerprint", ""))):
                raise ValidationError("locked edit fingerprint CAPTIONS diverso dal target")
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


def record_vertical_social_action_execution(path: Path, workstation_id: str, plan_id: str,
                                            fingerprint: str, action_id: str,
                                            expected_type: str, evidence: dict[str, Any]):
    """Record one executor's verified read-back without advancing unrelated actions."""
    plan = approved_vertical_social_plan(path, workstation_id, plan_id, fingerprint)
    action = plan.action(action_id)
    if action.action_type != expected_type:
        raise ValidationError("Tipo azione diverso dall'esecutore richiesto")
    if not isinstance(evidence, dict) or not evidence:
        raise ValidationError("Evidenza esecuzione azione mancante")
    store = VerticalSocialPlanStore(path, workstation_id)
    current = store.get(plan_id).action(action_id)
    if current.state == "APPROVED":
        transition_action(store, plan_id, action_id, "APPROVED", "APPLIED", evidence)
        current = store.get(plan_id).action(action_id)
    if current.state == "APPLIED":
        transition_action(store, plan_id, action_id, "APPLIED", "VERIFIED", evidence)
    elif current.state != "VERIFIED":
        raise ValidationError(f"{expected_type} non eseguibile nello stato {current.state}")
    return store.get(plan_id)


def mark_vertical_social_picture_lock(path: Path, workstation_id: str,
                                      plan_id: str,
                                      locked_edit_fingerprint: str) -> VerticalSocialWorkflowPlan:
    VerticalSocialPlanStore(path, workstation_id).get(plan_id)
    wrapped = _wrapped(path, plan_id)
    if wrapped.state != "APPROVED":
        raise ValidationError("Picture lock richiede piano approvato")
    if not isinstance(locked_edit_fingerprint, str) or len(locked_edit_fingerprint) != 64 \
            or any(character not in "0123456789abcdef" for character in locked_edit_fingerprint):
        raise ValidationError("locked edit fingerprint non valido")
    meta = _load_meta(path)
    meta[plan_id]["picture_locked"] = True
    meta[plan_id]["locked_edit_fingerprint"] = locked_edit_fingerprint
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
    if not spec.executable:
        raise ValidationError(f"{action.action_type} capability non validata")
    if next_state in {"APPLIED", "VERIFIED", "READY_FOR_REVIEW"}:
        raise ValidationError("Lo stato di esecuzione richiede l'esecutore dedicato")
    return transition_action(store, plan_id, action_id, action.state, next_state, evidence)


def inspect_vertical_social_plan(path: Path, workstation_id: str, plan_id: str) -> dict[str, Any]:
    plan = VerticalSocialPlanStore(path, workstation_id).get(plan_id)
    wrapped = _wrapped(path, plan_id)
    next_action = next_safe_action(plan)
    return {"plan_id": plan_id, "state": wrapped.state, "picture_locked": wrapped.picture_locked,
            "locked_edit_fingerprint": _load_meta(path).get(plan_id, {}).get("locked_edit_fingerprint"),
            "next_action": None if next_action is None else next_action.action_id,
            "actions": [action.to_dict() for action in plan.actions],
            "final_check": final_vertical_social_check(plan.to_dict(), wrapped.picture_locked)}


def compact_vertical_social_card(plan: VerticalSocialWorkflowPlan) -> dict[str, Any]:
    return {"card_count": 1, "plan_id": plan.plan_id, "state": plan.state,
            "picture_locked": plan.picture_locked}

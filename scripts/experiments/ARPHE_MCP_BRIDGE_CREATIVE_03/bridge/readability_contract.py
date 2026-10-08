from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any


CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
EXPECTED_REPOSITORY = "https://github.com/arphesegreteria-arch/arphe-graphic-kit.git"


class ReadabilityContractError(ValueError):
    pass


@dataclass(frozen=True)
class ReadabilityPolicy:
    policy: dict[str, Any]
    graphic_kit_repository: str
    graphic_kit_commit: str
    graphic_kit_policy_digest: str

    @property
    def schema_version(self) -> int:
        return int(self.policy["schema_version"])

    @property
    def policy_version(self) -> str:
        return str(self.policy["policy_version"])

    @property
    def canvases(self) -> dict[str, Any]:
        return self.policy["canvases"]

    @property
    def reading(self) -> dict[str, Any]:
        return self.policy["reading"]

    @property
    def review_body(self) -> dict[str, Any]:
        return self.policy["review_body"]

    @property
    def typography(self) -> dict[str, Any]:
        return self.policy["typography"]


def _mismatch(message: str) -> ReadabilityContractError:
    return ReadabilityContractError(f"{CONTRACT_MISMATCH}: {message}")


def _require_keys(value: object, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _mismatch(f"{location} deve essere un oggetto")
    if set(value) != expected:
        raise _mismatch(f"chiavi non valide in {location}")
    return value


def _number(value: object, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _mismatch(f"{location} deve essere numerico")
    result = float(value)
    if not math.isfinite(result):
        raise _mismatch(f"{location} deve essere finito")
    return result


def _validate_policy(value: object) -> dict[str, Any]:
    policy = _require_keys(
        value,
        {
            "schema_version",
            "policy_version",
            "canvases",
            "reading",
            "review_body",
            "typography",
            "technical_fallback_is_final",
        },
        "policy",
    )
    if _number(policy["schema_version"], "policy.schema_version") != 1:
        raise _mismatch("policy.schema_version non supportata")
    if policy["policy_version"] != "ARPHE_VIDEO_READABILITY_V1":
        raise _mismatch("policy_version non supportata")
    if policy["technical_fallback_is_final"] is not False:
        raise _mismatch("technical_fallback_is_final deve essere false")

    canvases = _require_keys(policy["canvases"], {"story_reel_1080x1920"}, "canvases")
    canvas = _require_keys(
        canvases["story_reel_1080x1920"],
        {"width", "height", "essential_safe_area"},
        "story_reel_1080x1920",
    )
    if _number(canvas["width"], "canvas.width") != 1080:
        raise _mismatch("canvas.width non valido")
    if _number(canvas["height"], "canvas.height") != 1920:
        raise _mismatch("canvas.height non valido")
    safe = _require_keys(
        canvas["essential_safe_area"], {"left", "right", "top", "bottom"}, "safe_area"
    )
    coordinates = [_number(safe[name], f"safe_area.{name}") for name in ("left", "right", "top", "bottom")]
    if coordinates != [0.08, 0.84, 0.10, 0.82]:
        raise _mismatch("safe area non canonica")

    reading = _require_keys(
        policy["reading"],
        {"words_per_second", "settle_seconds", "minimum_seconds", "standard_maximum_seconds"},
        "reading",
    )
    expected_reading = {
        "words_per_second": 4.0,
        "settle_seconds": 1,
        "minimum_seconds": 3,
        "standard_maximum_seconds": 12,
    }
    for name, expected in expected_reading.items():
        if _number(reading[name], f"reading.{name}") != expected:
            raise _mismatch(f"reading.{name} non canonico")

    body = _require_keys(policy["review_body"], {"size_tiers", "maximum_lines"}, "review_body")
    if body["size_tiers"] != [0.052, 0.047, 0.042]:
        raise _mismatch("size_tiers non canonici")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in body["size_tiers"]):
        raise _mismatch("size_tiers non numerici")
    if _number(body["maximum_lines"], "maximum_lines") != 7:
        raise _mismatch("maximum_lines non canonico")

    typography = _require_keys(
        policy["typography"], {"heading", "body", "label", "button"}, "typography"
    )
    expected_type = {
        "heading": ("Noto Serif Display", 300),
        "body": ("Satoshi", 400),
        "label": ("Satoshi", 500),
        "button": ("Satoshi", 700),
    }
    for role, (family, weight) in expected_type.items():
        entry = _require_keys(typography[role], {"family", "weight"}, f"typography.{role}")
        if entry["family"] != family or _number(entry["weight"], f"typography.{role}.weight") != weight:
            raise _mismatch(f"typography.{role} non canonica")
    return policy


def _canonical_digest(policy: dict[str, Any]) -> str:
    encoded = json.dumps(
        policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def contract_digest(policy: ReadabilityPolicy) -> str:
    return _canonical_digest(policy.policy)


def load_readability_contract(path: Path) -> ReadabilityPolicy:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _mismatch(f"contratto non leggibile: {exc}") from exc
    payload = _require_keys(
        payload,
        {
            "schema_version",
            "graphic_kit_repository",
            "graphic_kit_commit",
            "graphic_kit_policy_digest",
            "policy",
        },
        "contract",
    )
    if _number(payload["schema_version"], "contract.schema_version") != 1:
        raise _mismatch("contract.schema_version non supportata")
    if payload["graphic_kit_repository"] != EXPECTED_REPOSITORY:
        raise _mismatch("repository Graphic Kit non valida")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload["graphic_kit_commit"])):
        raise _mismatch("commit Graphic Kit non valido")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload["graphic_kit_policy_digest"])):
        raise _mismatch("digest Graphic Kit non valido")
    policy_data = _validate_policy(payload["policy"])
    policy = ReadabilityPolicy(
        policy=policy_data,
        graphic_kit_repository=payload["graphic_kit_repository"],
        graphic_kit_commit=payload["graphic_kit_commit"],
        graphic_kit_policy_digest=payload["graphic_kit_policy_digest"],
    )
    if contract_digest(policy) != policy.graphic_kit_policy_digest:
        raise _mismatch("digest dichiarato diverso dalla policy inclusa")
    return policy


def verify_graphic_kit_checkout(policy: ReadabilityPolicy, root: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    try:
        head = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"checkout Graphic Kit non valido: {exc}"]
    if head != policy.graphic_kit_commit:
        errors.append(f"commit atteso {policy.graphic_kit_commit}, trovato {head}")
    try:
        checkout_policy = json.loads(
            (root / "tokens" / "video-readability.json").read_text(encoding="utf-8")
        )
        digest = _canonical_digest(checkout_policy)
        if digest != policy.graphic_kit_policy_digest:
            errors.append(
                f"digest atteso {policy.graphic_kit_policy_digest}, trovato {digest}"
            )
        _validate_policy(checkout_policy)
    except (OSError, json.JSONDecodeError, ReadabilityContractError) as exc:
        errors.append(f"policy Graphic Kit non valida: {exc}")
    return errors

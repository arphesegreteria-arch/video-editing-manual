from __future__ import annotations

import argparse
import json
from pathlib import Path, PureWindowsPath
import re
from typing import Any


REQUIRED_FIELDS = {
    "schema_version",
    "workstation_id",
    "tunnel_name",
    "tunnel_id",
    "python_path",
    "pythonw_path",
    "python_version",
    "tunnel_client_path",
    "install_root",
    "log_dir",
    "creative_destination",
    "mcp_entrypoint",
    "requirements_path",
    "venv_root",
    "feature_flags",
}

PATH_FIELDS = {
    "python_path",
    "pythonw_path",
    "tunnel_client_path",
    "install_root",
    "log_dir",
    "creative_destination",
    "mcp_entrypoint",
    "requirements_path",
    "venv_root",
}

TUNNEL_NAMES = {
    "PC_PERSONALE": {"ARPHE-RESOLVE-PERSONALE"},
    "PC_SEGRETERIA": {"ARPHE-RESOLVE-SEGRETERIA", "ARPHE-RESOLVE-HOME"},
}


def _contains_secret(value: Any, key: str = "") -> bool:
    lowered = key.lower()
    if "api_key" in lowered or "secret" in lowered or "password" in lowered:
        return True
    if isinstance(value, str):
        return value.strip().lower().startswith("sk-")
    if isinstance(value, dict):
        return any(_contains_secret(child, str(child_key)) for child_key, child in value.items())
    if isinstance(value, list):
        return any(_contains_secret(child) for child in value)
    return False


def _normalize_windows_path(value: Any, field: str) -> str:
    text = str(value).strip()
    if not PureWindowsPath(text).is_absolute():
        raise ValueError(f"{field} must be an absolute Windows path")
    normalized = text.replace("\\", "/")
    if "/Microsoft/WindowsApps/" in normalized:
        raise ValueError(f"{field} cannot use a WindowsApps alias")
    return normalized


def validate_profile(raw: dict[str, Any], *, allow_placeholder_tunnel: bool = False) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("profile must be a JSON object")
    missing = sorted(REQUIRED_FIELDS - raw.keys())
    if missing:
        raise ValueError(f"profile is missing required fields: {', '.join(missing)}")
    if _contains_secret(raw):
        raise ValueError("profile contains secret or API key material")
    if raw["schema_version"] != 1:
        raise ValueError("schema_version must be 1")

    workstation = str(raw["workstation_id"]).strip()
    if workstation not in TUNNEL_NAMES:
        raise ValueError("workstation_id must be PC_PERSONALE or PC_SEGRETERIA")
    tunnel_name = str(raw["tunnel_name"]).strip()
    if tunnel_name not in TUNNEL_NAMES[workstation]:
        if workstation == "PC_PERSONALE" and tunnel_name in TUNNEL_NAMES["PC_SEGRETERIA"]:
            raise ValueError(f"tunnel name {tunnel_name} is reserved for PC_SEGRETERIA")
        raise ValueError(f"tunnel name {tunnel_name} is invalid for {workstation}")

    tunnel_id = str(raw["tunnel_id"]).strip()
    if not re.fullmatch(r"tunnel_[A-Za-z0-9_-]+", tunnel_id):
        raise ValueError("tunnel_id has an invalid format")
    if "REPLACE" in tunnel_id.upper() and not allow_placeholder_tunnel:
        raise ValueError("tunnel_id is still a placeholder")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(raw["python_version"]).strip()):
        raise ValueError("python_version must use major.minor.patch")

    flags = raw["feature_flags"]
    if not isinstance(flags, dict) or any(not isinstance(value, bool) for value in flags.values()):
        raise ValueError("feature_flags must be an object containing boolean values")

    normalized = dict(raw)
    normalized["workstation_id"] = workstation
    normalized["tunnel_name"] = tunnel_name
    normalized["tunnel_id"] = tunnel_id
    normalized["python_version"] = str(raw["python_version"]).strip()
    for field in PATH_FIELDS:
        normalized[field] = _normalize_windows_path(raw[field], field)
    return normalized


def load_profile(path: Path | str, *, allow_placeholder_tunnel: bool = False) -> dict[str, Any]:
    profile_path = Path(path)
    raw = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    return validate_profile(raw, allow_placeholder_tunnel=allow_placeholder_tunnel)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an ARPHE workstation deployment profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--profile", required=True)
    validate.add_argument("--allow-placeholder-tunnel", action="store_true")
    validate.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    try:
        profile = load_profile(args.profile, allow_placeholder_tunnel=args.allow_placeholder_tunnel)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.emit_json:
        print(json.dumps(profile, ensure_ascii=False, sort_keys=True))
    else:
        print(f"valid profile: {profile['workstation_id']} -> {profile['tunnel_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

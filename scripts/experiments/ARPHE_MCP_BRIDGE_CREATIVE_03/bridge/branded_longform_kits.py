from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .safety import ValidationError


HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
REQUIRED_PALETTE = frozenset({"ink", "teal", "neutral", "warm"})
REQUIRED_COMPONENTS = frozenset({
    "KEYWORD_BOX", "PROGRESSIVE_LIST", "PROCESS_STEPS",
    "COMPARISON_TABLE", "CHAPTER_CARD",
})


@dataclass(frozen=True)
class LongformKit:
    profile_id: str
    version: int
    font_family: str
    palette: dict[str, str]
    safe_area: dict[str, float]
    components: tuple[str, ...]


def load_longform_kits(path: Path) -> dict[str, LongformKit]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Kit longform non leggibile: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "kits"}:
        raise ValidationError("Registro kit longform non valido")
    if raw.get("schema_version") != 1 or not isinstance(raw.get("kits"), list):
        raise ValidationError("Versione registro kit longform non supportata")
    result: dict[str, LongformKit] = {}
    required = {"profile_id", "version", "font_family", "palette", "safe_area", "components"}
    for value in raw["kits"]:
        if not isinstance(value, dict) or set(value) != required:
            raise ValidationError("Definizione kit longform non valida")
        profile_id = str(value["profile_id"])
        if profile_id != "CARABELLESE_LONGFORM_EDITORIAL" or profile_id in result:
            raise ValidationError("Profilo kit longform sconosciuto o duplicato")
        palette = value["palette"]
        if (not isinstance(palette, dict) or set(palette) != REQUIRED_PALETTE
                or any(not isinstance(item, str) or not HEX.fullmatch(item)
                       for item in palette.values())):
            raise ValidationError("palette kit longform non valida")
        safe_area = value["safe_area"]
        if not isinstance(safe_area, dict) or set(safe_area) != {"left", "right", "top", "bottom"}:
            raise ValidationError("safe_area kit longform non valida")
        try:
            safe = {key: float(item) for key, item in safe_area.items()}
        except (TypeError, ValueError) as exc:
            raise ValidationError("safe_area kit longform non numerica") from exc
        if not (0 <= safe["left"] < safe["right"] <= 1
                and 0 <= safe["top"] < safe["bottom"] <= 1):
            raise ValidationError("safe_area kit longform fuori intervallo")
        components = value["components"]
        if (not isinstance(components, list) or len(components) != len(set(components))
                or set(components) != REQUIRED_COMPONENTS):
            raise ValidationError("components kit longform non validi")
        font = str(value["font_family"]).strip()
        if font != "Space Grotesk":
            raise ValidationError("font_family kit longform non approvata")
        version = value["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValidationError("version kit longform non valida")
        result[profile_id] = LongformKit(
            profile_id, version, font, dict(palette), safe, tuple(map(str, components)))
    if set(result) != {"CARABELLESE_LONGFORM_EDITORIAL"}:
        raise ValidationError("Kit Carabellese longform mancante")
    return result

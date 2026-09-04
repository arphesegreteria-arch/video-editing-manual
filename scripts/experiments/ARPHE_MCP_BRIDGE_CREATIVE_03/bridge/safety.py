from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Iterable


NAME_MAX = 64
REVIEW_TEXT_MAX = 800
SMALL_LABEL_MAX = 80
MAX_FRAME = 2_592_000
MAX_CREATIVE_FRAMES = 10_800
ALLOWED_RESOLUTIONS = {(1080, 1920), (1920, 1080), (1080, 1080)}
ALLOWED_FPS = {24.0, 25.0, 30.0}
COLOR_ROLES = {"ivory", "cream", "beige", "burgundy", "warm_brown", "dark_brown", "black", "white"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mxf"}
PRESET_NAMES = {"ARPHE_SOFT_DROP", "ARPHE_PAPER_STACK", "ARPHE_ELEGANT_REVEAL", "ARPHE_CTA_SETTLE"}


class ValidationError(ValueError):
    pass


def arphe_name(value: str, fallback: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Il nome deve essere una stringa")
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = fallback
    if not cleaned.upper().startswith("ARPHE_"):
        cleaned = "ARPHE_" + cleaned
    return cleaned[:NAME_MAX]


def require_arphe_name(value: str, kind: str = "nome") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"ARPHE_[A-Za-z0-9_-]{1,58}", value):
        raise ValidationError(f"{kind} deve iniziare con ARPHE_ e contenere solo lettere, numeri, _ o -")
    return value


def ensure_no_collision(name: str, existing: Iterable[str], kind: str) -> None:
    if name.casefold() in {str(item).casefold() for item in existing}:
        raise ValidationError(f"{kind} già esistente; overwrite vietato: {name}")


def validate_timeline_settings(width: int, height: int, fps: float) -> tuple[int, int, float]:
    if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int):
        raise ValidationError("width e height devono essere interi")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(float(fps)):
        raise ValidationError("fps deve essere numerico e finito")
    resolution = (width, height)
    frame_rate = float(fps)
    if resolution not in ALLOWED_RESOLUTIONS:
        raise ValidationError(f"Risoluzione non consentita: {resolution[0]}x{resolution[1]}")
    if frame_rate not in ALLOWED_FPS:
        raise ValidationError(f"FPS non consentiti: {frame_rate}")
    return resolution[0], resolution[1], frame_rate


def validate_frame_range(start_frame: int, end_frame: int) -> tuple[int, int]:
    if (isinstance(start_frame, bool) or isinstance(end_frame, bool)
            or not isinstance(start_frame, int) or not isinstance(end_frame, int)):
        raise ValidationError("I frame devono essere interi")
    start, end = start_frame, end_frame
    if start < 0 or end <= start or end > MAX_FRAME:
        raise ValidationError("Richiesto 0 <= start_frame < end_frame entro il limite di sicurezza")
    if end - start > MAX_CREATIVE_FRAMES:
        raise ValidationError("Durata creative oltre il limite di sicurezza")
    return start, end


def validate_review(text: str, stars: int, highlight_text: str | None, small_label: str | None) -> None:
    if not isinstance(text, str) or not text.strip() or len(text) > REVIEW_TEXT_MAX:
        raise ValidationError(f"Review text richiesto, massimo {REVIEW_TEXT_MAX} caratteri")
    if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5:
        raise ValidationError("stars deve essere un intero tra 1 e 5")
    if highlight_text is not None:
        if not isinstance(highlight_text, str) or not highlight_text.strip() or highlight_text not in text:
            raise ValidationError("highlight_text deve essere una sottostringa non vuota della recensione")
    if small_label is not None and (not isinstance(small_label, str) or len(small_label) > SMALL_LABEL_MAX):
        raise ValidationError(f"small_label massimo {SMALL_LABEL_MAX} caratteri")


def validate_palette(palette: dict[str, str]) -> None:
    if set(palette) != COLOR_ROLES:
        raise ValidationError("La palette deve contenere esattamente i ruoli colore ARPHE consentiti")
    for role, value in palette.items():
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValidationError(f"Colore non valido per {role}")


def validate_color_role(role: str) -> str:
    if role not in COLOR_ROLES:
        raise ValidationError(f"Ruolo colore non consentito: {role}")
    return role


def validate_preset(name: str) -> str:
    if name not in PRESET_NAMES:
        raise ValidationError(f"Preset non consentito: {name}")
    return name


def allowed_asset(path_value: str, root: Path, kind: str) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValidationError("Asset path richiesto")
    candidate = Path(path_value).expanduser().resolve(strict=True)
    root = root.expanduser().resolve(strict=True)
    if not candidate.is_file() or not candidate.is_relative_to(root):
        raise ValidationError("Asset fuori dalla cartella allowlisted")
    extensions = VIDEO_EXTENSIONS if kind == "video" else IMAGE_EXTENSIONS
    if candidate.suffix.lower() not in extensions:
        raise ValidationError(f"Estensione {candidate.suffix.lower()} non consentita per {kind}")
    return candidate


def finite_float(value: object, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{name} non valido")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} deve essere numerico") from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValidationError(f"{name} deve essere tra {minimum} e {maximum}")
    return result

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any

from .font_readiness import FontReadiness, TextMeasurer
from .readability_contract import ReadabilityPolicy


PASS = "PASS"
NEEDS_REVIEW = "NEEDS_REVIEW"
BLOCKED = "BLOCKED"
TOO_LONG_FOR_STANDARD = "TOO_LONG_FOR_STANDARD"
TEXT_OVERFLOW = "TEXT_OVERFLOW"
FONT_UNAVAILABLE = "FONT_UNAVAILABLE"
UNSAFE_LAYOUT = "UNSAFE_LAYOUT"
CONTRACT_MISMATCH = "CONTRACT_MISMATCH"


@dataclass(frozen=True)
class ReviewAssessment:
    status: str
    reason_codes: tuple[str, ...]
    word_count: int
    duration_seconds: int
    duration_frames: int
    selected_size: float | None
    line_count: int | None
    suggested_split: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "word_count": self.word_count,
            "duration_seconds": self.duration_seconds,
            "duration_frames": self.duration_frames,
            "selected_size": self.selected_size,
            "line_count": self.line_count,
            "suggested_split": self.suggested_split,
        }


@dataclass(frozen=True)
class SequenceAssessment:
    status: str
    reason_codes: tuple[str, ...]
    reviews: tuple[ReviewAssessment, ...]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "reviews": [review.to_dict() for review in self.reviews],
            "fingerprint": self.fingerprint,
        }


def _safe_measure(
    measurer: TextMeasurer,
    text: str,
    family: str,
    weight: int,
    font_size: float,
) -> float | None:
    try:
        width = float(measurer.measure_text(text, family, weight, font_size))
    except Exception:
        return None
    if not math.isfinite(width) or width < 0:
        return None
    return width


def _line_count_for_size(
    text: str,
    max_width: float,
    family: str,
    weight: int,
    font_size: float,
    measurer: TextMeasurer,
) -> int | None:
    lines = 0
    for explicit_line in text.split("\n"):
        lines += 1
        if explicit_line == "":
            continue
        current = ""
        for token in re.findall(r"\S+|[ \t]+", explicit_line):
            if not token.isspace():
                token_width = _safe_measure(measurer, token, family, weight, font_size)
                if token_width is None or token_width > max_width:
                    return None
            candidate = current + token
            candidate_width = _safe_measure(measurer, candidate, family, weight, font_size)
            if candidate_width is None:
                return None
            if candidate_width <= max_width:
                current = candidate
                continue
            lines += 1
            current = "" if token.isspace() else token
    return lines


def _fit_text(
    text: str,
    policy: ReadabilityPolicy,
    canvas_id: str,
    measurer: TextMeasurer,
) -> tuple[float | None, int | None]:
    canvas = policy.canvases[canvas_id]
    safe = canvas["essential_safe_area"]
    canvas_width = float(canvas["width"])
    max_width = canvas_width * (float(safe["right"]) - float(safe["left"]))
    role = policy.typography["body"]
    last_count: int | None = None
    for tier in policy.review_body["size_tiers"]:
        font_size = float(tier) * canvas_width
        line_count = _line_count_for_size(
            text,
            max_width,
            str(role["family"]),
            int(role["weight"]),
            font_size,
            measurer,
        )
        if line_count is None:
            continue
        last_count = line_count
        if line_count <= int(policy.review_body["maximum_lines"]):
            return float(tier), line_count
    return None, last_count


def _duration(text: str, fps: float, policy: ReadabilityPolicy) -> tuple[int, int, int]:
    count = len(re.findall(r"\S+", text))
    reading = policy.reading
    seconds = max(
        int(reading["minimum_seconds"]),
        math.ceil(count / float(reading["words_per_second"]))
        + int(reading["settle_seconds"]),
    )
    frames = round(seconds * fps) if math.isfinite(fps) and fps > 0 else 0
    return count, seconds, frames


def assess_review(
    text: str,
    canvas_id: str,
    fps: float,
    policy: ReadabilityPolicy,
    measurer: TextMeasurer,
    fonts: FontReadiness,
) -> ReviewAssessment:
    if not isinstance(text, str):
        text = ""
    word_count, seconds, frames = _duration(text, fps, policy)
    if canvas_id not in policy.canvases or not math.isfinite(fps) or fps <= 0:
        return ReviewAssessment(
            BLOCKED,
            (CONTRACT_MISMATCH,),
            word_count,
            seconds,
            frames,
            None,
            None,
        )
    if not fonts.ready:
        return ReviewAssessment(
            BLOCKED,
            (FONT_UNAVAILABLE,),
            word_count,
            seconds,
            frames,
            None,
            None,
        )
    if not text.strip():
        return ReviewAssessment(
            BLOCKED,
            (TEXT_OVERFLOW,),
            word_count,
            seconds,
            frames,
            None,
            0,
        )

    selected_size, line_count = _fit_text(text, policy, canvas_id, measurer)
    reasons: list[str] = []
    if selected_size is None:
        reasons.append(TEXT_OVERFLOW)
    if seconds > int(policy.reading["standard_maximum_seconds"]):
        reasons.append(TOO_LONG_FOR_STANDARD)
    if TEXT_OVERFLOW in reasons:
        status = BLOCKED
    elif reasons:
        status = NEEDS_REVIEW
    else:
        status = PASS
    return ReviewAssessment(
        status,
        tuple(reasons),
        word_count,
        seconds,
        frames,
        selected_size,
        line_count,
    )


def suggest_sentence_split(
    text: str,
    measurer: TextMeasurer,
    policy: ReadabilityPolicy,
) -> int | None:
    if not isinstance(text, str) or not text.strip():
        return None
    canvas_id = "story_reel_1080x1920"
    if canvas_id not in policy.canvases:
        return None
    candidates = [
        match.end()
        for match in re.finditer(r"[.!?](?=\s|$)", text)
        if text[: match.end()].strip() and text[match.end() :].strip()
    ]
    if not candidates:
        return None
    valid = [
        offset
        for offset in candidates
        if _fit_text(text[:offset], policy, canvas_id, measurer)[0] is not None
        and _fit_text(text[offset:], policy, canvas_id, measurer)[0] is not None
    ]
    if not valid:
        return None
    role = policy.typography["body"]
    size = float(policy.review_body["size_tiers"][-1]) * float(
        policy.canvases[canvas_id]["width"]
    )
    total_width = _safe_measure(
        measurer, text, str(role["family"]), int(role["weight"]), size
    )
    if total_width is None:
        return None

    def distance(offset: int) -> tuple[float, int]:
        left_width = _safe_measure(
            measurer, text[:offset], str(role["family"]), int(role["weight"]), size
        )
        if left_width is None:
            return (math.inf, offset)
        return (abs(left_width - total_width / 2.0), offset)

    return min(valid, key=distance)


def assess_sequence(
    reviews: list[dict],
    canvas_id: str,
    fps: float,
    policy: ReadabilityPolicy,
    measurer: TextMeasurer,
    fonts: FontReadiness,
) -> SequenceAssessment:
    assessments: list[ReviewAssessment] = []
    split_candidates: list[int | None] = []
    fingerprint_reviews: list[dict[str, Any]] = []
    for review in reviews:
        text = review.get("text", "") if isinstance(review, dict) else ""
        stars = review.get("stars") if isinstance(review, dict) else None
        assessment = assess_review(text, canvas_id, fps, policy, measurer, fonts)
        split = suggest_sentence_split(text, measurer, policy)
        assessment = ReviewAssessment(
            assessment.status,
            assessment.reason_codes,
            assessment.word_count,
            assessment.duration_seconds,
            assessment.duration_frames,
            assessment.selected_size,
            assessment.line_count,
            split,
        )
        assessments.append(assessment)
        split_candidates.append(split)
        fingerprint_reviews.append({"text": text, "stars": stars, "split_candidate": split})

    if any(item.status == BLOCKED for item in assessments):
        status = BLOCKED
    elif any(item.status == NEEDS_REVIEW for item in assessments):
        status = NEEDS_REVIEW
    else:
        status = PASS
    reason_order = (
        CONTRACT_MISMATCH,
        FONT_UNAVAILABLE,
        UNSAFE_LAYOUT,
        TEXT_OVERFLOW,
        TOO_LONG_FOR_STANDARD,
    )
    present = {reason for item in assessments for reason in item.reason_codes}
    reasons = tuple(reason for reason in reason_order if reason in present)
    fingerprint_payload = {
        "reviews": fingerprint_reviews,
        "canvas_id": canvas_id,
        "fps": fps,
        "policy_version": policy.policy_version,
        "policy_digest": policy.graphic_kit_policy_digest,
    }
    canonical = json.dumps(
        fingerprint_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    fingerprint = hashlib.sha256(canonical).hexdigest()
    return SequenceAssessment(status, reasons, tuple(assessments), fingerprint)

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import math
import os
from typing import Protocol

from .readability_contract import ReadabilityPolicy


FONT_UNAVAILABLE = "FONT_UNAVAILABLE"
LF_FACESIZE = 32
DEFAULT_CHARSET = 1
OUT_DEFAULT_PRECIS = 0
CLIP_DEFAULT_PRECIS = 0
DEFAULT_QUALITY = 0
DEFAULT_PITCH = 0
FF_DONTCARE = 0
LOGPIXELSY = 90


class TextMeasurer(Protocol):
    def font_available(self, family: str, weight: int) -> bool: ...

    def measure_text(self, text: str, family: str, weight: int, font_size: float) -> float: ...


@dataclass(frozen=True)
class FontReadiness:
    ready: bool
    required: tuple[tuple[str, int], ...]
    missing: tuple[tuple[str, int], ...]
    diagnostic: str | None = None

    @property
    def reason_code(self) -> str | None:
        return None if self.ready else FONT_UNAVAILABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "reason_code": self.reason_code,
            "required": [
                {"family": family, "weight": weight} for family, weight in self.required
            ],
            "missing": [
                {"family": family, "weight": weight} for family, weight in self.missing
            ],
            "diagnostic": self.diagnostic,
        }


class LOGFONTW(ctypes.Structure):
    _fields_ = [
        ("lfHeight", wintypes.LONG),
        ("lfWidth", wintypes.LONG),
        ("lfEscapement", wintypes.LONG),
        ("lfOrientation", wintypes.LONG),
        ("lfWeight", wintypes.LONG),
        ("lfItalic", wintypes.BYTE),
        ("lfUnderline", wintypes.BYTE),
        ("lfStrikeOut", wintypes.BYTE),
        ("lfCharSet", wintypes.BYTE),
        ("lfOutPrecision", wintypes.BYTE),
        ("lfClipPrecision", wintypes.BYTE),
        ("lfQuality", wintypes.BYTE),
        ("lfPitchAndFamily", wintypes.BYTE),
        ("lfFaceName", wintypes.WCHAR * LF_FACESIZE),
    ]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class WindowsGdiTextMeasurer:
    """Measure text and enumerate exact Windows GDI family/weight pairs."""

    def __init__(self) -> None:
        self.available = False
        self.unavailable_reason = "Windows GDI non disponibile su questa piattaforma"
        self._gdi32 = None
        if os.name != "nt":
            return
        try:
            self._gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            self._configure_signatures()
            dc = self._gdi32.CreateCompatibleDC(None)
            if not dc:
                raise OSError(ctypes.get_last_error(), "CreateCompatibleDC failed")
            self._gdi32.DeleteDC(dc)
        except (AttributeError, OSError) as exc:
            self.unavailable_reason = f"Windows GDI non inizializzabile: {exc}"
            return
        self.available = True
        self.unavailable_reason = ""

    def _configure_signatures(self) -> None:
        assert self._gdi32 is not None
        self._gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self._gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self._gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self._gdi32.DeleteDC.restype = wintypes.BOOL
        self._gdi32.CreateFontW.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        ]
        self._gdi32.CreateFontW.restype = wintypes.HANDLE
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        self._gdi32.SelectObject.restype = wintypes.HANDLE
        self._gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        self._gdi32.GetTextExtentPoint32W.argtypes = [
            wintypes.HDC,
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(SIZE),
        ]
        self._gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL
        self._gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
        self._gdi32.GetDeviceCaps.restype = ctypes.c_int

    def _require_available(self) -> None:
        if not self.available or self._gdi32 is None:
            raise RuntimeError(self.unavailable_reason)

    def font_available(self, family: str, weight: int) -> bool:
        if not self.available or self._gdi32 is None:
            return False
        dc = self._gdi32.CreateCompatibleDC(None)
        if not dc:
            return False
        found = False
        logical_font = LOGFONTW()
        logical_font.lfCharSet = DEFAULT_CHARSET
        logical_font.lfFaceName = family[: LF_FACESIZE - 1]
        callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
            ctypes.c_int,
            ctypes.POINTER(LOGFONTW),
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.LPARAM,
        )

        def inspect(logfont, _metric, _font_type, _lparam):
            nonlocal found
            face = str(logfont.contents.lfFaceName).casefold()
            if face == family.casefold() and int(logfont.contents.lfWeight) == int(weight):
                found = True
                return 0
            return 1

        callback = callback_type(inspect)
        self._gdi32.EnumFontFamiliesExW.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(LOGFONTW),
            callback_type,
            wintypes.LPARAM,
            wintypes.DWORD,
        ]
        self._gdi32.EnumFontFamiliesExW.restype = ctypes.c_int
        try:
            self._gdi32.EnumFontFamiliesExW(dc, ctypes.byref(logical_font), callback, 0, 0)
            return found
        finally:
            self._gdi32.DeleteDC(dc)

    def measure_text(self, text: str, family: str, weight: int, font_size: float) -> float:
        self._require_available()
        if not isinstance(text, str):
            raise TypeError("text deve essere una stringa")
        if not math.isfinite(font_size) or font_size <= 0:
            raise ValueError("font_size deve essere finito e positivo")
        if not self.font_available(family, weight):
            raise ValueError(f"font non disponibile: {family} {weight}")
        if not text:
            return 0.0
        assert self._gdi32 is not None
        dc = self._gdi32.CreateCompatibleDC(None)
        if not dc:
            raise OSError(ctypes.get_last_error(), "CreateCompatibleDC failed")
        font = None
        previous = None
        try:
            dpi = self._gdi32.GetDeviceCaps(dc, LOGPIXELSY) or 96
            height = -max(1, round(font_size * dpi / 72.0))
            font = self._gdi32.CreateFontW(
                height,
                0,
                0,
                0,
                int(weight),
                0,
                0,
                0,
                DEFAULT_CHARSET,
                OUT_DEFAULT_PRECIS,
                CLIP_DEFAULT_PRECIS,
                DEFAULT_QUALITY,
                DEFAULT_PITCH | FF_DONTCARE,
                family,
            )
            if not font:
                raise OSError(ctypes.get_last_error(), "CreateFontW failed")
            previous = self._gdi32.SelectObject(dc, font)
            if not previous:
                raise OSError(ctypes.get_last_error(), "SelectObject failed")
            size = SIZE()
            if not self._gdi32.GetTextExtentPoint32W(dc, text, len(text), ctypes.byref(size)):
                raise OSError(ctypes.get_last_error(), "GetTextExtentPoint32W failed")
            return float(size.cx)
        finally:
            if previous:
                self._gdi32.SelectObject(dc, previous)
            if font:
                self._gdi32.DeleteObject(font)
            self._gdi32.DeleteDC(dc)


def check_required_fonts(policy: ReadabilityPolicy, measurer: TextMeasurer) -> FontReadiness:
    required = tuple(
        sorted(
            {
                (str(role["family"]), int(role["weight"]))
                for role in policy.typography.values()
            }
        )
    )
    missing: list[tuple[str, int]] = []
    diagnostics: list[str] = []
    for family, weight in required:
        try:
            present = measurer.font_available(family, weight)
        except Exception as exc:
            present = False
            diagnostics.append(f"{family} {weight}: {type(exc).__name__}")
        if not present:
            missing.append((family, weight))
    return FontReadiness(
        ready=not missing,
        required=required,
        missing=tuple(missing),
        diagnostic="; ".join(diagnostics) or None,
    )

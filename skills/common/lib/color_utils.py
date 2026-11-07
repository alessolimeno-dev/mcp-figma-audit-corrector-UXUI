"""
color_utils.py — Motore condiviso di analisi e modulazione colore W3C WCAG 2.2.
Librerie esterne ufficiali supportate con fallback automatico a 0 token AI:
- wcag-contrast-ratio (https://pypi.org/project/wcag-contrast-ratio/)
- colorbrew (https://pypi.org/project/colorbrew/)
- colorsys (Libreria nativa Python Standard Library)
"""

from typing import Tuple, Dict, Any, Optional
import colorsys

# 1. Libreria ufficiale PyPI: wcag-contrast-ratio
_wcag_cr_lib: Any = None
try:
    import wcag_contrast_ratio as _wcr  # type: ignore
    _wcag_cr_lib = _wcr
    HAS_WCAG_CONTRAST_RATIO = True
except ImportError:
    HAS_WCAG_CONTRAST_RATIO = False

# 2. Libreria ufficiale PyPI: colorbrew
_colorbrew_cls: Any = None
try:
    from colorbrew import Color as _cb_color  # type: ignore
    _colorbrew_cls = _cb_color
    HAS_COLORBREW = True
except ImportError:
    HAS_COLORBREW = False


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Converte una stringa esadecimale (#RGB o #RRGGBB) in tupla RGB (0-255)."""
    s = hex_str.strip().lstrip('#')
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"Formato esadecimale non valido: {hex_str}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def hex_to_rgb_unit(hex_str: str) -> Tuple[float, float, float]:
    """Converte #RRGGBB in tupla normalizzata (0.0 - 1.0) richiesta da wcag-contrast-ratio."""
    r, g, b = hex_to_rgb(hex_str)
    return (r / 255.0, g / 255.0, b / 255.0)


def relative_luminance(r: int, g: int, b: int) -> float:
    """Calcola la luminanza relativa secondo la formula ufficiale W3C WCAG 2.2."""
    def channel(val: int) -> float:
        c = val / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    """
    Calcola il rapporto di contrasto W3C richiamando le librerie ufficiali:
    1. wcag-contrast-ratio (se installata)
    2. colorbrew (se installata)
    3. Formula matematica W3C nativa integrata come fallback.
    """
    if HAS_WCAG_CONTRAST_RATIO and _wcag_cr_lib is not None:
        ratio = _wcag_cr_lib.rgb(hex_to_rgb_unit(hex1), hex_to_rgb_unit(hex2))
        return round(float(ratio), 2)

    if HAS_COLORBREW and _colorbrew_cls is not None:
        c1 = _colorbrew_cls(hex1)
        c2 = _colorbrew_cls(hex2)
        if hasattr(c1, "contrast_ratio"):
            return round(float(c1.contrast_ratio(c2)), 2)

    l1 = relative_luminance(*hex_to_rgb(hex1))
    l2 = relative_luminance(*hex_to_rgb(hex2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Converte valori RGB (0-255) in stringa #RRGGBB."""
    return f"#{max(0, min(255, int(round(r)))):02X}{max(0, min(255, int(round(g)))):02X}{max(0, min(255, int(round(b)))):02X}"


def adjust_lightness_for_contrast(fg_hex: str, bg_hex: str, target_ratio: float = 4.5) -> str:
    """
    Ricalcola il colore del testo/elemento modulando la luminosità (Lightness) in spazio HLS
    tramite `colorsys` e verificando ogni step con `contrast_ratio`,
    per raggiungere il target WCAG preservando la tonalità istituzionale del brand (Hue).
    """
    if contrast_ratio(fg_hex, bg_hex) >= target_ratio:
        return fg_hex

    r, g, b = hex_to_rgb(fg_hex)
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)

    bg_lum = relative_luminance(*hex_to_rgb(bg_hex))
    should_darken = bg_lum > 0.5

    best_hex = fg_hex
    steps = 100
    for i in range(1, steps + 1):
        if should_darken:
            new_l = max(0.0, l - (i / float(steps)) * l)
        else:
            new_l = min(1.0, l + (i / float(steps)) * (1.0 - l))

        nr, ng, nb = colorsys.hls_to_rgb(h, new_l, s)
        candidate_hex = rgb_to_hex(nr * 255.0, ng * 255.0, nb * 255.0)

        if contrast_ratio(candidate_hex, bg_hex) >= target_ratio:
            return candidate_hex
        best_hex = candidate_hex

    return best_hex


def calculate_padding_expansion(width: float, height: float, min_size: float = 24.0) -> Dict[str, Any]:
    """Calcola il padding minimo orizzontale e verticale necessario per raggiungere 24x24 px (WCAG 2.5.8)."""
    delta_w = max(0.0, min_size - width)
    delta_h = max(0.0, min_size - height)
    return {
        "target_width": max(width, min_size),
        "target_height": max(height, min_size),
        "padding_horizontal_add": round(delta_w / 2.0, 1),
        "padding_vertical_add": round(delta_h / 2.0, 1),
        "compliant": (width >= min_size and height >= min_size)
    }

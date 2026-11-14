"""
wcag_checks.py — Misure deterministiche WCAG condivise da checker.py (audit) e corrector.py (correzione).

Qui vive l'UNICA implementazione di:
- check_contrast / check_target_size (WCAG 1.4.3, 1.4.6, 1.4.11, 2.5.5, 2.5.8)
- measure(): sceglie la misura giusta a partire da un dizionario di misure
  ({"fg","bg"} oppure {"w","h"}) e restituisce esito, testo leggibile e valori calcolati.
- parse_measures_from_text(): rilegge fg/bg o WxH dalla colonna Descrizione del report Excel.

I valori misurati NON vengono mai scritti a mano dal modello: arrivano da qui.
"""

import re
import colorsys
from typing import Any, Dict, Optional

try:
    from .color_utils import (
        HAS_WCAG_CONTRAST_RATIO,
        HAS_COLORBREW,
        _wcag_cr_lib,
        _colorbrew_cls,
        hex_to_rgb,
        relative_luminance,
        contrast_ratio,
        adjust_lightness_for_contrast,
        calculate_padding_expansion,
    )
    from .normative import WCAG_CRITERIA
except ImportError:  # esecuzione con path diverso
    from common.lib.color_utils import (  # type: ignore
        HAS_WCAG_CONTRAST_RATIO,
        HAS_COLORBREW,
        _wcag_cr_lib,
        _colorbrew_cls,
        hex_to_rgb,
        relative_luminance,
        contrast_ratio,
        adjust_lightness_for_contrast,
        calculate_padding_expansion,
    )
    from common.lib.normative import WCAG_CRITERIA  # type: ignore


HEX_RE = r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b"


# ==============================================================================
# CONTRASTO E TARGET
# ==============================================================================

def required_contrast(riferimento: str = "", is_large_text: bool = False, is_ui_component: bool = False) -> float:
    """Soglia di contrasto richiesta: 3.0 (testo grande / componenti UI 1.4.11), 7.0 (AAA 1.4.6), altrimenti 4.5."""
    ref = str(riferimento)
    if is_ui_component or "1.4.11" in ref:
        return 3.0
    if "1.4.6" in ref:
        return 4.5 if is_large_text else 7.0
    return 3.0 if is_large_text else 4.5


def check_contrast(fg_hex: str, bg_hex: str, is_large_text: bool = False, is_ui_component: bool = False) -> Dict[str, Any]:
    """
    Verifica la conformità WCAG 1.4.3 (AA), 1.4.6 (AAA) e 1.4.11 (AA) tramite
    wcag-contrast-ratio e colorbrew (con fallback nativo automatico).
    """
    ratio = contrast_ratio(fg_hex, bg_hex)
    threshold = 3.0 if (is_large_text or is_ui_component) else 4.5
    criterio_num = "1.4.11" if is_ui_component else "1.4.3"
    wcag_info = WCAG_CRITERIA.get(criterio_num, {})

    passes_aa = ratio >= threshold
    passes_aaa = ratio >= (4.5 if is_large_text else 7.0)

    if HAS_WCAG_CONTRAST_RATIO and _wcag_cr_lib is not None and not is_ui_component:
        passes_aa = bool(_wcag_cr_lib.passes_AA(ratio, large=is_large_text))
        passes_aaa = bool(_wcag_cr_lib.passes_AAA(ratio, large=is_large_text))

    suggested_text = None
    if HAS_COLORBREW and _colorbrew_cls is not None:
        try:
            bg_c = _colorbrew_cls(bg_hex)
            if hasattr(bg_c, "suggest_text_color"):
                suggested_text = str(bg_c.suggest_text_color())
        except Exception:
            suggested_text = None
    elif not passes_aa:
        r, g, b = hex_to_rgb(fg_hex)
        h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        bg_lum = relative_luminance(*hex_to_rgb(bg_hex))
        should_darken = bg_lum > 0.5
        for step in range(1, 101):
            new_l = max(0.0, l - (step / 100.0) * l) if should_darken else min(1.0, l + (step / 100.0) * (1.0 - l))
            nr, ng, nb = colorsys.hls_to_rgb(h, new_l, s)
            cand = f"#{int(round(nr*255)):02X}{int(round(ng*255)):02X}{int(round(nb*255)):02X}"
            if contrast_ratio(cand, bg_hex) >= threshold:
                suggested_text = cand
                break

    return {
        "criterio": f"WCAG {criterio_num} (AA)",
        "nome_criterio": wcag_info.get("nome", "Contrasto"),
        "w3c_url": wcag_info.get("url", ""),
        "techniques": wcag_info.get("techniques", []),
        "ratio": ratio,
        "threshold": threshold,
        "compliant": passes_aa,
        "passes_AAA": passes_aaa,
        "fg": fg_hex,
        "bg": bg_hex,
        "suggested_text_colorbrew": suggested_text,
        "engine": (
            "wcag-contrast-ratio + colorbrew"
            if (HAS_WCAG_CONTRAST_RATIO or HAS_COLORBREW)
            else "W3C Standard Formula (wcag-contrast-ratio compatible)"
        ),
    }


def check_target_size(w: float, h: float) -> Dict[str, Any]:
    """Verifica conformità WCAG 2.5.8 (minimo 24x24 px) e WCAG 2.5.5 (AAA 44x44 px)."""
    compliant = (w >= 24.0 and h >= 24.0)
    wcag_info = WCAG_CRITERIA.get("2.5.8", {})
    return {
        "criterio": "WCAG 2.5.8 (AA)",
        "w3c_url": wcag_info.get("url", "https://www.w3.org/TR/WCAG22/#target-size-minimum"),
        "techniques": wcag_info.get("techniques", ["C42"]),
        "width": w,
        "height": h,
        "compliant": compliant,
        "recommended_mobile_AAA_2_5_5": (w >= 44.0 and h >= 44.0),
    }


# ==============================================================================
# MISURA UNIFICATA (usata da checker e corrector)
# ==============================================================================

def _num(v: Any) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _hls(hex_str: str) -> Dict[str, float]:
    r, g, b = hex_to_rgb(hex_str)
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return {"h": round(h * 360.0, 1), "l": round(l * 100.0, 1), "s": round(s * 100.0, 1)}


def _figma_rgb(hex_str: str) -> Dict[str, float]:
    r, g, b = hex_to_rgb(hex_str)
    return {"r": round(r / 255.0, 4), "g": round(g / 255.0, 4), "b": round(b / 255.0, 4)}


def measure(riferimento: str, misure: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Calcola la misura richiesta dalle `misure` di una voce.

    misure contrasto : {"fg": "#888888", "bg": "#FFFFFF", "testo_grande": false, "componente_ui": false}
    misure target    : {"w": 18, "h": 18}   (px; "min": 44 per forzare la soglia, altrimenti 24 o 44 se WCAG 2.5.5)

    Restituisce None se `misure` non contiene dati sufficienti. Altrimenti:
      kind, compliant, soglia, testo (frase pronta per Excel/Log) e i valori numerici calcolati,
      incluso — se non conforme — il colore corretto a tonalità costante (HLS) o il padding da aggiungere.
    """
    if not misure:
        return None
    ref = str(riferimento or "")

    if misure.get("fg") and misure.get("bg"):
        fg, bg = str(misure["fg"]).upper(), str(misure["bg"]).upper()
        large = bool(misure.get("testo_grande", False))
        ui = bool(misure.get("componente_ui", False)) or "1.4.11" in ref
        soglia = required_contrast(ref, large, ui)
        ratio = contrast_ratio(fg, bg)
        ok = ratio >= soglia
        out: Dict[str, Any] = {
            "kind": "contrasto", "fg": fg, "bg": bg, "ratio": ratio, "soglia": soglia,
            "compliant": ok, "testo_grande": large, "componente_ui": ui,
            "testo": f"Misurato: {fg} su {bg} = {ratio}:1 (soglia {_num(soglia)}:1) -> {'conforme' if ok else 'NON conforme'}",
        }
        if not ok:
            new_fg = adjust_lightness_for_contrast(fg, bg, soglia)
            out["suggerito_fg"] = new_fg
            out["suggerito_ratio"] = contrast_ratio(new_fg, bg)
            out["hls_prima"] = _hls(fg)
            out["hls_dopo"] = _hls(new_fg)
            out["figma_rgb_suggerito"] = _figma_rgb(new_fg)
            out["suggerito_raggiunge_soglia"] = out["suggerito_ratio"] >= soglia
        return out

    if misure.get("w") is not None and misure.get("h") is not None:
        w, h = float(misure["w"]), float(misure["h"])
        minimo = float(misure.get("min") or (44.0 if "2.5.5" in ref else 24.0))
        ok = w >= minimo and h >= minimo
        out = {
            "kind": "target", "w": w, "h": h, "soglia": minimo, "compliant": ok,
            "testo": f"Misurato: {_num(w)}x{_num(h)} px (minimo {_num(minimo)}x{_num(minimo)} px) -> {'conforme' if ok else 'NON conforme'}",
        }
        if not ok:
            pad = calculate_padding_expansion(w, h, minimo)
            out["padding_orizzontale_per_lato"] = pad["padding_horizontal_add"]
            out["padding_verticale_per_lato"] = pad["padding_vertical_add"]
            out["dimensione_finale"] = [pad["target_width"], pad["target_height"]]
        return out

    return None


# ==============================================================================
# LETTURA DELLE MISURE DALLA DESCRIZIONE EXCEL
# ==============================================================================

def parse_measures_from_text(text: str, riferimento: str = "") -> Optional[Dict[str, Any]]:
    """
    Ricava le misure da un testo di Descrizione. Ha priorità la frase scritta da checker.py
    ("Misurato: #FG su #BG = ..." / "Misurato: WxH px ..."); in sua assenza prova il formato libero
    "#FG su #BG" o "WxH px". Restituisce None se non riesce: in quel caso le misure vanno lette da Figma.
    """
    if not text:
        return None
    ref = str(riferimento or "")
    low = text.lower()
    scope = text.split("Misurato:", 1)[1] if "Misurato:" in text else text

    colori = re.findall(HEX_RE, scope)
    if len(colori) >= 2 and ("1.4." in ref or not ref):
        return {
            "fg": colori[0].upper(), "bg": colori[1].upper(),
            "testo_grande": ("testo grande" in low or "large text" in low),
            "componente_ui": "1.4.11" in ref,
        }

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(?:px)?", scope, flags=re.I)
    if m and ("2.5." in ref or not ref):
        return {"w": float(m.group(1).replace(",", ".")), "h": float(m.group(2).replace(",", "."))}
    return None

"""
normative.py — Loader e parser unificato per WCAG 2.2 e 10 Euristiche di Nielsen.
Carica il dizionario ufficiale a 0 token AI da references/wcag.json.
"""

import os
import json
import re
from typing import Dict, Any


def load_wcag_library() -> Dict[str, Any]:
    """Carica in memoria locale il dizionario normativo wcag.json senza consumare token AI."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(base_dir, "..", "references", "wcag.json")),
        os.path.normpath(os.path.join(base_dir, "..", "..", "common", "references", "wcag.json")),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"criteria": {}, "usability_heuristics_source": {"heuristics": {}}}


WCAG_LIBRARY: Dict[str, Any] = load_wcag_library()
WCAG_CRITERIA: Dict[str, Dict[str, Any]] = WCAG_LIBRARY.get("criteria", {})
NIELSEN_HEURISTICS: Dict[str, Dict[str, Any]] = (
    WCAG_LIBRARY.get("usability_heuristics_source", {}).get("heuristics", {})
)


def extract_wcag_num(ref: str) -> str:
    """Estrae il codice numerico del criterio WCAG (es. 'WCAG 1.4.3 (AA)' -> '1.4.3')."""
    if not ref:
        return ""
    m = re.search(r"(\d+\.\d+\.\d+)", str(ref))
    return m.group(1) if m else ""


def lookup_normative_entry(ref: str) -> Dict[str, Any]:
    """Restituisce i metadati ufficiali dal dizionario W3C wcag.json o dalle 10 Euristiche di Nielsen."""
    if not ref:
        return {}
    ref_clean = str(ref).strip()
    if ref_clean in NIELSEN_HEURISTICS:
        return NIELSEN_HEURISTICS[ref_clean]

    m_ux = re.search(r"(UX-en-\d+)", ref_clean, re.IGNORECASE)
    if m_ux:
        key = m_ux.group(1)
        for k, v in NIELSEN_HEURISTICS.items():
            if k.lower() == key.lower():
                return v

    num = extract_wcag_num(ref_clean)
    if num and num in WCAG_CRITERIA:
        return WCAG_CRITERIA[num]
    return {}

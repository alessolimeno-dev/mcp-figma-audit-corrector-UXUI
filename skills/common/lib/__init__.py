"""
skills.common.lib — Moduli condivisi per le skill di audit e correzione Figma.
Fornisce funzioni a 0 token per:
- Calcolo contrasto e modulazione colore W3C (color_utils)
- Normative WCAG 2.2 ed Euristiche di Nielsen (normative)
- Gestione fogli di calcolo OpenXML / OpenPyXL (excel_utils)
"""

from .color_utils import (
    HAS_WCAG_CONTRAST_RATIO,
    HAS_COLORBREW,
    hex_to_rgb,
    hex_to_rgb_unit,
    relative_luminance,
    contrast_ratio,
    rgb_to_hex,
    adjust_lightness_for_contrast,
    calculate_padding_expansion,
)
from .normative import (
    load_wcag_library,
    lookup_normative_entry,
    extract_wcag_num,
    WCAG_LIBRARY,
    WCAG_CRITERIA,
    NIELSEN_HEURISTICS,
)
from .excel_utils import (
    HAS_OPENPYXL,
    openpyxl,
    OPENXML_NAMESPACES,
)

__all__ = [
    "HAS_WCAG_CONTRAST_RATIO",
    "HAS_COLORBREW",
    "hex_to_rgb",
    "hex_to_rgb_unit",
    "relative_luminance",
    "contrast_ratio",
    "rgb_to_hex",
    "adjust_lightness_for_contrast",
    "calculate_padding_expansion",
    "load_wcag_library",
    "lookup_normative_entry",
    "extract_wcag_num",
    "WCAG_LIBRARY",
    "WCAG_CRITERIA",
    "NIELSEN_HEURISTICS",
    "HAS_OPENPYXL",
    "openpyxl",
    "OPENXML_NAMESPACES",
]

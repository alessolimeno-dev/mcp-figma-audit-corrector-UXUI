"""
excel_utils.py — Utility condivise per la manipolazione di fogli Excel .xlsx.
Supporta:
- openpyxl (se disponibile nell'ambiente)
- fallback nativo basato su zipfile e xml.etree.ElementTree (a 0 dipendenze)
"""

from typing import Any, Dict

# Rilevamento OpenPyXL
openpyxl: Any = None
try:
    import openpyxl as _openpyxl  # type: ignore
    openpyxl = _openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

OPENXML_NAMESPACES = {
    'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}

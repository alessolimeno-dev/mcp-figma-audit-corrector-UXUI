#!/usr/bin/env python3
"""
checker.py — Motore deterministico universale per la Skill 1 (Agente di Audit)
Architettura a 0 Token AI basata su librerie e dataset standard ufficiali:
- Calcolo e analisi colore:
  * wcag-contrast-ratio (https://pypi.org/project/wcag-contrast-ratio/)
  * colorbrew (https://pypi.org/project/colorbrew/)
- Dizionario normativo Accessibilità e Tecniche HTML/ARIA:
  * W3C Official WCAG 2.2 JSON (skills/common/references/wcag.json — https://www.w3.org/WAI/WCAG22/wcag.json)
  * Include tutti gli 86 criteri di successo (A, AA, AAA), tecniche ufficiali (H37, ARIA14, H42, G18, ecc.) e link W3C
- Usabilità:
  * 10 Euristiche di Jakob Nielsen (Nielsen, 1994a CHI '94; Nielsen, 1994b; NN/g https://www.nngroup.com/articles/ten-usability-heuristics/)
- Compilazione automatica a 0 token della colonna 'Suggerimento (Annotazioni in Figma)'
"""

import math
import sys
import json
import shutil
import io
import re
import os
import zipfile
import argparse
import colorsys  # Libreria nativa Python (Standard Library) per conversioni RGB <-> HLS
from datetime import datetime
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Tuple, Optional

# ==============================================================================
# IMPORT MODULI CONDIVISI (skills.common.lib)
# ==============================================================================
_current_dir = os.path.dirname(os.path.abspath(__file__))
_skills_dir = os.path.normpath(os.path.join(_current_dir, "..", ".."))
_repo_root = os.path.normpath(os.path.join(_current_dir, "..", "..", ".."))
for _p in [_repo_root, _skills_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from skills.common.lib.color_utils import (
        HAS_WCAG_CONTRAST_RATIO,
        HAS_COLORBREW,
        _wcag_cr_lib,
        _colorbrew_cls,
        hex_to_rgb,
        hex_to_rgb_unit,
        relative_luminance,
        contrast_ratio,
    )
    from skills.common.lib.normative import (
        load_wcag_library,
        lookup_normative_entry,
        extract_wcag_num,
        WCAG_LIBRARY,
        WCAG_CRITERIA,
        NIELSEN_HEURISTICS,
    )
    from skills.common.lib.excel_utils import (
        HAS_OPENPYXL,
        openpyxl,
    )
    from skills.common.lib.wcag_checks import (
        check_contrast,
        check_target_size,
        measure,
    )
except ImportError:
    from common.lib.color_utils import (  # type: ignore
        HAS_WCAG_CONTRAST_RATIO,
        HAS_COLORBREW,
        _wcag_cr_lib,
        _colorbrew_cls,
        hex_to_rgb,
        hex_to_rgb_unit,
        relative_luminance,
        contrast_ratio,
    )
    from common.lib.normative import (  # type: ignore
        load_wcag_library,
        lookup_normative_entry,
        extract_wcag_num,
        WCAG_LIBRARY,
        WCAG_CRITERIA,
        NIELSEN_HEURISTICS,
    )
    from common.lib.excel_utils import (  # type: ignore
        HAS_OPENPYXL,
        openpyxl,
    )
    from common.lib.wcag_checks import (  # type: ignore
        check_contrast,
        check_target_size,
        measure,
    )

_load_wcag_library = load_wcag_library


def apply_measurements(item: Dict[str, Any], is_violation: bool = True) -> Dict[str, Any]:
    """
    Calcola con check_contrast / check_target_size (tramite `measure`) i valori di una voce che
    porta `misure` ({"fg","bg"} oppure {"w","h"}) e sovrascrive i numeri scritti dal modello.

    Restituisce {"descrizione","correzione","affidabilita","motivo","avvisi"}: campi da riversare nella
    voce. Se `misure` manca, restituisce {} (la voce resta com'è: valori non misurati dallo script).
    """
    ref = item.get("riferimento") or item.get("ref", "")
    m = measure(ref, item.get("misure") or {})
    if not m:
        return {}

    avvisi: List[str] = []
    desc = (item.get("descrizione") or item.get("nota") or "").strip()
    corr = (item.get("correzione") or item.get("azione") or "").strip()
    affid = item.get("affidabilita", "Alta")
    motivo = (item.get("motivo") or "").strip()
    voce_id = item.get("id") or item.get("elemento", "?")

    # Numeri del modello in conflitto con la misura: la misura vince, ma lo si segnala.
    if m["kind"] == "contrasto":
        for num in re.findall(r"(\d+(?:\.\d+)?)\s*:\s*1", desc):
            if abs(float(num) - m["ratio"]) > 0.05:
                avvisi.append(f"{voce_id}: la descrizione dice {num}:1, lo script misura {m['ratio']}:1 (vale la misura).")
        # il rapporto scritto dal modello viene sempre rimosso: resta solo quello misurato
        desc = re.sub(r"\s*\(\s*(?:ratio\s*)?\d+(?:\.\d+)?\s*:\s*1\s*\)|\s*(?:ratio\s*)?\d+(?:\.\d+)?\s*:\s*1", "", desc).strip()

    desc = f"{desc} | {m['testo']}" if desc else m["testo"]

    if is_violation and m["compliant"]:
        avvisi.append(f"{voce_id}: segnalata come violazione ma la misura è conforme ({m['testo']}).")
        affid = "Da controllare"
        motivo = (motivo + " " if motivo else "") + "La misura dello script risulta conforme: verificare la segnalazione."
    if not is_violation and not m["compliant"]:
        avvisi.append(f"{voce_id}: in 'corretto' ma la misura NON è conforme ({m['testo']}).")

    if is_violation and not m["compliant"] and not corr:
        if m["kind"] == "contrasto":
            corr = (f"Portare il colore da {m['fg']} a {m['suggerito_fg']} (stessa tonalità, "
                    f"contrasto {m['suggerito_ratio']}:1 su {m['bg']})")
        else:
            corr = (f"Portare il target a {m['dimensione_finale'][0]:g}x{m['dimensione_finale'][1]:g} px "
                    f"(+{m['padding_orizzontale_per_lato']:g}px orizzontale e +{m['padding_verticale_per_lato']:g}px verticale per lato)")

    return {"descrizione": desc, "correzione": corr, "affidabilita": affid, "motivo": motivo, "avvisi": avvisi, "misura": m}



def check_target_distance(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """Calcola la distanza minima tra due bounding box (x, y, width, height)."""
    x1, y1, w1, h1 = box1['x'], box1['y'], box1['width'], box1['height']
    x2, y2, w2, h2 = box2['x'], box2['y'], box2['width'], box2['height']
    dx = max(0.0, x2 - (x1 + w1), x1 - (x2 + w2))
    dy = max(0.0, y2 - (y1 + h1), y1 - (y2 + h2))
    return math.hypot(dx, dy)


def check_auto_layout_text(node_layout: Dict[str, Any]) -> Dict[str, Any]:
    """Verifica WCAG 1.4.4 / 1.4.10 sul rischio di troncamento testo o assenza di Auto Layout."""
    has_auto_layout = node_layout.get("layoutMode") in ["HORIZONTAL", "VERTICAL"]
    vertical_sizing = node_layout.get("layoutSizingVertical", "")
    text_auto_resize = node_layout.get("textAutoResize", "")

    issues = []
    if not has_auto_layout:
        issues.append("Contenitore privo di Auto Layout: rischio reflow/troncamento testo (WCAG 1.4.4/1.4.10)")
    elif vertical_sizing == "FIXED" and text_auto_resize != "HEIGHT":
        issues.append("Altezza fissa rigida (FIXED) su frame di testo: rischio troncamento al 200% (WCAG 1.4.4)")

    return {
        "criterio": "WCAG 1.4.4 / 1.4.10 (AA)",
        "compliant": len(issues) == 0,
        "issues": issues
    }


# ==============================================================================
# VALUTAZIONE DETERMINISTICA CAMPI EXCEL E SUGGERIMENTO ANNOTAZIONI FIGMA
# ==============================================================================

def evaluate_ambito(riferimento: str) -> str:
    """Determina l'ambito (Usabilità o Accessibilità) dal dizionario W3C / Nielsen."""
    if not riferimento:
        return ""
    entry = lookup_normative_entry(riferimento)
    if entry.get("ambito"):
        return entry["ambito"]
    ref_clean = str(riferimento).strip().upper()
    if ref_clean.startswith("UX") or ref_clean.startswith("N-") or "NIELSEN" in ref_clean:
        return "Usabilità"
    return "Accessibilità"


def evaluate_stato(riferimento: str) -> str:
    """Determina lo stato di verifica standard attingendo da references/wcag.json."""
    if not riferimento:
        return ""
    entry = lookup_normative_entry(riferimento)
    if entry.get("stato"):
        return entry["stato"]
    ref = str(riferimento)
    if "2.1.1" in ref or "4.1.2" in ref:
        return "Non verificabile"
    if any(k in ref for k in ["1.3.1", "1.4.4", "1.4.10", "1.4.12", "2.4.3", "2.4.11"]):
        return "Da verificare sul sito"
    return "Verificata"


def evaluate_dove_si_corregge(riferimento: str, descrizione: str = "", correzione: str = "") -> str:
    """Determina 'Dove si corregge (Figma / Codice)' dal dizionario ufficiale wcag.json."""
    if not riferimento and not descrizione and not correzione:
        return ""
    text_combined = f"{descrizione} {correzione}".lower()
    if any(kw in text_combined for kw in ["aria-label", "attributo alt", "tag semantici", "<h1>", "markup semantico"]):
        return "Figma (Annotazione) + Codice"
    entry = lookup_normative_entry(riferimento)
    if entry.get("dove"):
        return entry["dove"]
    return "Prototipo Figma"


def evaluate_suggerimento_annotazione(
    riferimento: str,
    elemento: str = "",
    descrizione: str = "",
    correzione: str = "",
    annotazione_presente: bool = False
) -> str:
    """
    Genera deterministicamente a 0 token il suggerimento per la nuova colonna
    'Suggerimento (Annotazioni in Figma)' attingendo dalle Tecniche W3C in references/wcag.json.
    Non impone il testo editoriale dell'aria-label o dell'alt, ma indica il codice/attributo da annotare.
    """
    if annotazione_presente:
        return "Annotazione già presente in Figma"

    el_low = f"{elemento} {descrizione} {correzione}".lower()
    entry = lookup_normative_entry(riferimento)
    base_sugg = entry.get("annotazione_figma", "-")

    # Affinamento contestuale in base al tipo di elemento UI (immagini, pulsanti solo-icona, form, titoli)
    if any(k in el_low for k in ["solo-icona", "solo icona", "icon button", "pulsante icona", "hamburger", "lente", "carrello"]):
        if "1.4.3" not in str(riferimento) and "2.5.8" not in str(riferimento):
            return (
                "Inserire annotazione in Figma (Tecnica W3C ARIA14): "
                "<button type=\"button\" aria-label=\"[azione del pulsante]\"> con <svg aria-hidden=\"true\">."
            )
    if any(k in el_low for k in ["immagine decorativa", "sfondo decorativo", "icona decorativa"]):
        return "Inserire annotazione in Figma (Tecnica W3C H67): marcare come decorativa con alt=\"\" o aria-hidden=\"true\"."
    if any(k in el_low for k in ["hero image", "immagine", "foto", "illustrazione", "logo", "banner"]) and "1.1.1" in str(riferimento):
        return (
            "Inserire annotazione in Figma (Tecnica W3C H37/H67): "
            "per immagine informativa <img alt=\"[descrizione funzione/contenuto]\">; "
            "se puramente decorativa alt=\"\"."
        )

    return base_sugg if base_sugg else "-"


def normalize_gravita(val: Any) -> str:
    """Normalizza la gravità in etichetta testuale (Lieve, Moderata, Grave, Bloccante)."""
    if val is None or val == "":
        return ""
    v_str = str(val).strip().lower()
    if v_str in ['1', 'lieve']:
        return "Lieve"
    elif v_str in ['2', 'moderata', 'moderato']:
        return "Moderata"
    elif v_str in ['3', 'grave']:
        return "Grave"
    elif v_str in ['4', 'bloccante']:
        return "Bloccante"
    return str(val)


def calculate_riepilogo_stats(voci: List[Dict[str, Any]], session_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Calcola deterministicamente in Python la matrice di Riepilogo inserendo gli ID delle voci.
    """
    matrix_ids = {
        ('Usabilità', 'Lieve'): [],
        ('Usabilità', 'Moderata'): [],
        ('Usabilità', 'Grave'): [],
        ('Usabilità', 'Bloccante'): [],
        ('Accessibilità', 'Lieve'): [],
        ('Accessibilità', 'Moderata'): [],
        ('Accessibilità', 'Grave'): [],
        ('Accessibilità', 'Bloccante'): []
    }

    stato_ids = {'Verificata': [], 'Da verificare sul sito': [], 'Non verificabile': []}
    affidabilita_ids = {'Alta': [], 'Da controllare': [], 'Non verificabile': []}
    conflitto_ids = []
    dove_ids = {
        'Prototipo Figma': [],
        'Prototipo Figma + Codice': [],
        'Figma (Annotazione) + Codice': [],
        'Codice (Front-end)': []
    }
    annotazioni_suggerite_ids = []

    gravita_col_map = {'Lieve': 'B', 'Moderata': 'C', 'Grave': 'D', 'Bloccante': 'E'}

    for item in voci:
        v_id = item.get('id', '')
        ref = item.get('riferimento', '')
        elem = item.get('elemento', '')
        desc = item.get('descrizione', '')
        corr = item.get('correzione', '')
        ambito = item.get('ambito') or evaluate_ambito(ref)
        gravita = normalize_gravita(item.get('gravita'))
        stato = item.get('stato') or evaluate_stato(ref)
        dove = item.get('dove_si_corregge') or evaluate_dove_si_corregge(ref, desc, corr)
        sugg_ann = item.get('suggerimento_annotazione') or evaluate_suggerimento_annotazione(
            ref, elem, desc, corr, bool(item.get('annotazione_presente', False))
        )
        affidabilita = item.get('affidabilita', '')
        conflitto = item.get('conflitto', '')

        item['ambito'] = ambito
        item['gravita'] = gravita
        item['stato'] = stato
        item['dove_si_corregge'] = dove
        item['suggerimento_annotazione'] = sugg_ann

        key = (ambito, gravita)
        if key in matrix_ids and v_id:
            matrix_ids[key].append(v_id)
        if stato in stato_ids and v_id:
            stato_ids[stato].append(v_id)
        if affidabilita in affidabilita_ids and v_id:
            affidabilita_ids[affidabilita].append(v_id)
        if str(conflitto).strip().lower() in ['sì', 'si', 'yes', 'true'] and v_id:
            conflitto_ids.append(v_id)
        if dove in dove_ids and v_id:
            dove_ids[dove].append(v_id)
        if sugg_ann and sugg_ann not in ['-', 'Annotazione già presente in Figma'] and v_id:
            annotazioni_suggerite_ids.append(v_id)

    def fmt_ids(ids_list: List[str]) -> str:
        return ", ".join(ids_list) if ids_list else "-"

    def fmt_total(ids_list: List[str]) -> str:
        if not ids_list:
            return "- (0)"
        return f"{', '.join(ids_list)} ({len(ids_list)})"

    stats: Dict[str, Any] = {}

    for row_num, amb in [(4, 'Usabilità'), (5, 'Accessibilità')]:
        row_all_ids = []
        for grav, col in gravita_col_map.items():
            ids = matrix_ids.get((amb, grav), [])
            stats[f'{col}{row_num}'] = fmt_ids(ids)
            row_all_ids.extend(ids)
        stats[f'F{row_num}'] = fmt_total(row_all_ids)

    total_all_ids = []
    for grav, col in gravita_col_map.items():
        col_ids = matrix_ids.get(('Usabilità', grav), []) + matrix_ids.get(('Accessibilità', grav), [])
        stats[f'{col}6'] = fmt_total(col_ids)
        total_all_ids.extend(col_ids)
    stats['F6'] = f"{len(total_all_ids)} voci totali"

    stats['B10'] = fmt_total(stato_ids['Verificata'])
    stats['B11'] = fmt_total(stato_ids['Da verificare sul sito'])
    stats['B12'] = fmt_total(stato_ids['Non verificabile'])

    stats['B16'] = fmt_total(affidabilita_ids['Alta'])
    stats['B17'] = fmt_total(affidabilita_ids['Da controllare'])
    stats['B18'] = fmt_total(affidabilita_ids['Non verificabile'])

    stats['B22'] = fmt_total(conflitto_ids)

    stats['B46'] = fmt_total(dove_ids['Prototipo Figma'])
    stats['B47'] = fmt_total(dove_ids['Prototipo Figma + Codice'])
    stats['B48'] = fmt_total(dove_ids['Figma (Annotazione) + Codice'])
    stats['B49'] = fmt_total(dove_ids['Codice (Front-end)'])

    # Riga aggiuntiva in Riepilogo: Annotazioni Figma suggerite
    stats['A50'] = 'Voci con Suggerimento Annotazione Figma'
    stats['B50'] = fmt_total(annotazioni_suggerite_ids)

    return stats


def _inject_cached_values(xlsx_path: str, sheet_cache: Dict[str, Dict[str, Any]]):
    """Inietta i valori pre-calcolati da Python direttamente nel pacchetto XML OpenXML (.xlsx)."""
    ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    ET.register_namespace('', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')

    buf = io.BytesIO()
    with zipfile.ZipFile(xlsx_path, 'r') as zin:
        wb_root = ET.fromstring(zin.read('xl/workbook.xml'))
        rels_root = ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))

        rel_targets = {}
        for r in rels_root:
            r_id = r.attrib.get('Id')
            t = r.attrib.get('Target', '').lstrip('/')
            if not t.startswith('xl/'):
                t = 'xl/' + t
            rel_targets[r_id] = t

        sheet_map = {}
        for s in wb_root.findall('.//ns:sheet', ns):
            s_name = s.attrib.get('name')
            r_id = s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            if r_id and r_id in rel_targets:
                sheet_map[s_name] = rel_targets[r_id]

        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                for s_name, file_target in sheet_map.items():
                    if item.filename == file_target and s_name in sheet_cache:
                        root = ET.fromstring(data)
                        updates = sheet_cache[s_name]
                        for c in root.findall('.//ns:c', ns):
                            coord = c.attrib.get('r')
                            if coord in updates:
                                val_str = str(updates[coord])
                                v_el = c.find('ns:v', ns)
                                if v_el is None:
                                    v_el = ET.SubElement(c, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                                v_el.text = val_str
                        data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                zout.writestr(item, data)

    with open(xlsx_path, 'wb') as f:
        f.write(buf.getvalue())


def compile_audit_report(
    template_path: str,
    output_path: str,
    session_data: Dict[str, Any],
    voci_data: List[Dict[str, Any]],
    corretto_data: List[Dict[str, Any]]
) -> str:
    """
    Compila deterministicamente l'audit report clonando Audit_modello.xlsx.
    Include:
    - Colonna P 'Suggerimento (Annotazioni in Figma)' nel foglio Voci (23 colonne: A-Q Agente, R-W Progettista)
    """
    shutil.copyfile(template_path, output_path)
    stats = calculate_riepilogo_stats(voci_data, session_data)

    if not HAS_OPENPYXL:
        return _compile_audit_report_xml(output_path, session_data, voci_data, corretto_data, stats)

    wb = openpyxl.load_workbook(output_path)

    # 1. Rimuove foglio Istruzioni
    if 'Istruzioni' in wb.sheetnames:
        del wb['Istruzioni']

    # 2. Compila Sessione
    s_sess = wb['Sessione']
    s_sess.cell(4, 2, session_data.get('caso', ''))
    s_sess.cell(5, 2, session_data.get('file_figma', ''))
    s_sess.cell(6, 2, session_data.get('link_figma', ''))
    s_sess.cell(7, 2, session_data.get('versione', 'v0'))
    s_sess.cell(8, 1, 'Data e Timestamp analisi')
    s_sess.cell(8, 2, session_data.get('timestamp', ''))
    s_sess.cell(9, 2, session_data.get('pagine', ''))
    s_sess.cell(10, 2, session_data.get('agente', 'Agente di Audit v2.0 (W3C wcag.json + wcag-contrast-ratio + colorbrew)'))
    s_sess.cell(11, 2, session_data.get('estensione', 'Figma MCP Connector'))
    s_sess.cell(12, 1, 'Modello e versione AI')
    s_sess.cell(12, 2, session_data.get('modello', ''))
    s_sess.cell(13, 2, session_data.get('note', ''))

    # 3. Compila Voci (23 colonne: A-Q Agente con P='Suggerimento (Annotazioni in Figma)', R-W Progettista)
    s_voci = wb['Voci']
    s_voci.cell(1, 4, 'ID Nodo Figma')
    s_voci.cell(1, 8, 'Gravità (Lieve, Moderata, Grave, Bloccante)')
    s_voci.cell(1, 15, 'Dove si corregge (Figma / Codice)')
    s_voci.cell(1, 16, 'Suggerimento (Annotazioni in Figma)')
    s_voci.cell(1, 17, 'Fonte della segnalazione')
    s_voci.cell(1, 18, 'Decisione')
    s_voci.cell(1, 19, 'Motivo della decisione')
    s_voci.cell(1, 20, 'Tipo di motivo')
    s_voci.cell(1, 21, 'Gravità confermata')
    s_voci.cell(1, 22, 'Chi applica la correzione')
    s_voci.cell(1, 23, 'Data della decisione')

    for idx, item in enumerate(voci_data):
        r = idx + 2
        ref = item.get('riferimento', '')
        elem = item.get('elemento', '')
        desc = item.get('descrizione', '')
        corr = item.get('correzione', '')
        ambito = item.get('ambito') or evaluate_ambito(ref)
        stato = item.get('stato') or evaluate_stato(ref)
        gravita = normalize_gravita(item.get('gravita'))
        dove = item.get('dove_si_corregge') or evaluate_dove_si_corregge(ref, desc, corr)
        sugg_ann = item.get('suggerimento_annotazione') or evaluate_suggerimento_annotazione(
            ref, elem, desc, corr, bool(item.get('annotazione_presente', False))
        )

        s_voci.cell(r, 1, item.get('id', ''))
        s_voci.cell(r, 2, item.get('pagina', ''))
        s_voci.cell(r, 3, elem)
        s_voci.cell(r, 4, item.get('nodo_id') or item.get('node_id') or item.get('id_nodo') or '')
        s_voci.cell(r, 5, ambito)
        s_voci.cell(r, 6, ref)
        s_voci.cell(r, 7, desc)
        s_voci.cell(r, 8, gravita)
        s_voci.cell(r, 9, stato)
        s_voci.cell(r, 10, item.get('affidabilita', ''))
        s_voci.cell(r, 11, item.get('motivo', ''))
        s_voci.cell(r, 12, item.get('conflitto', 'No'))
        s_voci.cell(r, 13, item.get('motivo_conflitto', ''))
        s_voci.cell(r, 14, corr)
        s_voci.cell(r, 15, dove)
        s_voci.cell(r, 16, sugg_ann)
        s_voci.cell(r, 17, item.get('fonte', 'Agente di audit'))

    # 4. Compila Corretto
    s_corr = wb['Corretto']
    for idx, item in enumerate(corretto_data):
        r = idx + 2
        ref = item.get('riferimento', '')
        ambito = item.get('ambito') or evaluate_ambito(ref)
        s_corr.cell(r, 1, ambito)
        s_corr.cell(r, 2, item.get('pagina', ''))
        s_corr.cell(r, 3, item.get('elemento', ''))
        s_corr.cell(r, 4, item.get('descrizione', ''))
        s_corr.cell(r, 5, ref)

    # 5. Compila Riepilogo
    s_riep = wb['Riepilogo']
    s_riep['B3'] = 'Lieve'
    s_riep['C3'] = 'Moderata'
    s_riep['D3'] = 'Grave'
    s_riep['E3'] = 'Bloccante'
    s_riep['F3'] = 'Totale'

    for coord, val in stats.items():
        s_riep[coord] = val

    wb.save(output_path)
    _inject_cached_values(output_path, {'Riepilogo': stats})
    return output_path


def _compile_audit_report_xml(
    output_path: str,
    session_data: Dict[str, Any],
    voci_data: List[Dict[str, Any]],
    corretto_data: List[Dict[str, Any]],
    stats: Dict[str, Any]
) -> str:
    """Fallback OpenXML puro in libreria standard Python quando openpyxl non è installato."""
    NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('', NS)
    ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')

    def qn(tag: str) -> str:
        return f'{{{NS}}}{tag}'

    def set_inline_str(row_el: ET.Element, coord: str, text: str, default_style: str = '25'):
        c = None
        for cell in row_el.findall(qn('c')):
            if cell.attrib.get('r') == coord:
                c = cell
                break
        if c is None:
            c = ET.SubElement(row_el, qn('c'), {'r': coord, 's': default_style})
        style = c.attrib.get('s', default_style)
        c.clear()
        c.attrib.update({'r': coord, 's': style, 't': 'inlineStr'})
        is_el = ET.SubElement(c, qn('is'))
        t_el = ET.SubElement(is_el, qn('t'))
        t_el.text = str(text)

    def get_or_create_row(sd: ET.Element, rn: int) -> ET.Element:
        for row in sd.findall(qn('row')):
            if int(row.attrib.get('r', '0')) == rn:
                return row
        new_r = ET.SubElement(sd, qn('row'), {'r': str(rn)})
        return new_r

    buf = io.BytesIO()
    with zipfile.ZipFile(output_path, 'r') as zin:
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == 'xl/worksheets/sheet1.xml':
                    continue
                data = zin.read(item.filename)
                if item.filename == '[Content_Types].xml':
                    ct_root = ET.fromstring(data)
                    for ov in list(ct_root):
                        if ov.attrib.get('PartName') == '/xl/worksheets/sheet1.xml':
                            ct_root.remove(ov)
                    data = ET.tostring(ct_root, encoding='utf-8', xml_declaration=True)
                elif item.filename == 'xl/_rels/workbook.xml.rels':
                    rels_root = ET.fromstring(data)
                    for rel in list(rels_root):
                        if rel.attrib.get('Target', '').endswith('sheet1.xml'):
                            rels_root.remove(rel)
                    data = ET.tostring(rels_root, encoding='utf-8', xml_declaration=True)
                elif item.filename == 'xl/workbook.xml':
                    wb_root = ET.fromstring(data)
                    sheets_el = wb_root.find(qn('sheets'))
                    if sheets_el is not None:
                        for s_el in list(sheets_el):
                            if s_el.attrib.get('name') == 'Istruzioni':
                                sheets_el.remove(s_el)
                    dn_el = wb_root.find(qn('definedNames'))
                    if dn_el is not None:
                        for d_el in dn_el.findall(qn('definedName')):
                            if d_el.attrib.get('localSheetId') == '2':
                                d_el.set('localSheetId', '1')
                    data = ET.tostring(wb_root, encoding='utf-8', xml_declaration=True)
                elif item.filename == 'xl/worksheets/sheet2.xml':
                    root = ET.fromstring(data)
                    sd = root.find(qn('sheetData'))
                    sess_map = {
                        4: ('Caso / Progetto analizzato', session_data.get('caso', '')),
                        5: ('File Figma analizzato (nome)', session_data.get('file_figma', '')),
                        6: ('Link al file Figma', session_data.get('link_figma', '')),
                        7: ('Versione del file (per esempio v0 pre-audit)', session_data.get('versione', 'v0')),
                        8: ('Data e Timestamp analisi', session_data.get('timestamp', '')),
                        9: ('Pagine analizzate', session_data.get('pagine', '')),
                        10: ('Agente di audit e librerie richiamate', session_data.get('agente', '')),
                        11: ('Estensione Figma e versione', session_data.get('estensione', '')),
                        12: ('Modello e versione AI', session_data.get('modello', '')),
                        13: ('Note', session_data.get('note', '')),
                    }
                    if sd is not None:
                        for rn, (label_txt, val_txt) in sess_map.items():
                            row = get_or_create_row(sd, rn)
                            set_inline_str(row, f'A{rn}', label_txt, '21')
                            set_inline_str(row, f'B{rn}', val_txt, '22')
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                elif item.filename == 'xl/worksheets/sheet3.xml':
                    root = ET.fromstring(data)
                    sd = root.find(qn('sheetData'))
                    if sd is not None:
                        header_row = get_or_create_row(sd, 1)
                        headers_map = [
                            ('D', 'ID Nodo Figma', '23'),
                            ('H', 'Gravità (Lieve, Moderata, Grave, Bloccante)', '23'),
                            ('O', 'Dove si corregge (Figma / Codice)', '23'),
                            ('P', 'Suggerimento (Annotazioni in Figma)', '23'),
                            ('Q', 'Fonte della segnalazione', '23'),
                            ('R', 'Decisione', '24'),
                            ('S', 'Motivo della decisione', '24'),
                            ('T', 'Tipo di motivo', '24'),
                            ('U', 'Gravità confermata', '24'),
                            ('V', 'Chi applica la correzione', '24'),
                            ('W', 'Data della decisione', '24'),
                        ]
                        for col_let, h_txt, st_id in headers_map:
                            set_inline_str(header_row, f'{col_let}1', h_txt, st_id)

                        for idx, v_item in enumerate(voci_data):
                            rn = idx + 2
                            row_el = get_or_create_row(sd, rn)
                            ref = v_item.get('riferimento', '')
                            elem = v_item.get('elemento', '')
                            desc = v_item.get('descrizione', '')
                            corr = v_item.get('correzione', '')
                            ambito = v_item.get('ambito') or evaluate_ambito(ref)
                            stato = v_item.get('stato') or evaluate_stato(ref)
                            gravita = normalize_gravita(v_item.get('gravita'))
                            dove = v_item.get('dove_si_corregge') or evaluate_dove_si_corregge(ref, desc, corr)
                            sugg_ann = v_item.get('suggerimento_annotazione') or evaluate_suggerimento_annotazione(
                                ref, elem, desc, corr, bool(v_item.get('annotazione_presente', False))
                            )
                            vals = [
                                ('A', v_item.get('id', '')),
                                ('B', v_item.get('pagina', '')),
                                ('C', elem),
                                ('D', v_item.get('nodo_id') or v_item.get('node_id') or ''),
                                ('E', ambito),
                                ('F', ref),
                                ('G', desc),
                                ('H', gravita),
                                ('I', stato),
                                ('J', v_item.get('affidabilita', '')),
                                ('K', v_item.get('motivo', '')),
                                ('L', v_item.get('conflitto', 'No')),
                                ('M', v_item.get('motivo_conflitto', '')),
                                ('N', corr),
                                ('O', dove),
                                ('P', sugg_ann),
                                ('Q', v_item.get('fonte', 'Agente di audit')),
                            ]
                            for col_let, val_txt in vals:
                                set_inline_str(row_el, f'{col_let}{rn}', val_txt, '25')
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                elif item.filename == 'xl/worksheets/sheet4.xml':
                    root = ET.fromstring(data)
                    sd = root.find(qn('sheetData'))
                    if sd is not None:
                        for idx, c_item in enumerate(corretto_data):
                            rn = idx + 2
                            row_el = get_or_create_row(sd, rn)
                            ref = c_item.get('riferimento', '')
                            ambito = c_item.get('ambito') or evaluate_ambito(ref)
                            for col_let, val_txt in [
                                ('A', ambito),
                                ('B', c_item.get('pagina', '')),
                                ('C', c_item.get('elemento', '')),
                                ('D', c_item.get('descrizione', '')),
                                ('E', ref),
                            ]:
                                set_inline_str(row_el, f'{col_let}{rn}', val_txt, '25')
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                elif item.filename == 'xl/worksheets/sheet5.xml':
                    root = ET.fromstring(data)
                    sd = root.find(qn('sheetData'))
                    if sd is not None:
                        for coord, val_txt in stats.items():
                            m_coord = re.match(r"([A-Z]+)(\d+)", coord)
                            if m_coord:
                                rn = int(m_coord.group(2))
                                row_el = get_or_create_row(sd, rn)
                                set_inline_str(row_el, coord, str(val_txt), '27')
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                zout.writestr(item, data)

    with open(output_path, 'wb') as f:
        f.write(buf.getvalue())
    return output_path


def compile_from_json(template_path: str, output_path: str, data: Dict[str, Any]) -> str:
    """
    Compila il report Excel a partire da un micro-payload JSON.
    Espande automaticamente a 0 token tutti i dati da references/wcag.json (86 criteri W3C + 10 Nielsen),
    inclusa la nuova colonna 'Suggerimento (Annotazioni in Figma)'.
    """
    raw_sess = data.get("session", {})
    session_data = {
        "caso": raw_sess.get("caso", "Prototipo Figma"),
        "file_figma": raw_sess.get("file_figma", "Prototipo"),
        "link_figma": raw_sess.get("link_figma", ""),
        "versione": raw_sess.get("versione", "v0 (pre-audit)"),
        "timestamp": raw_sess.get("timestamp", datetime.now().isoformat(timespec="seconds")),
        "pagine": raw_sess.get("pagine", "Desktop e Mobile"),
        "agente": raw_sess.get(
            "agente",
            "Agente di Audit v2.0 (W3C wcag.json + wcag-contrast-ratio + colorbrew)"
        ),
        "estensione": raw_sess.get("estensione", "Figma MCP Connector v2.0"),
        "modello": raw_sess.get("modello", "LLM Assistant"),
        "note": raw_sess.get(
            "note",
            "Report generato a 0 token tramite checker.py, W3C wcag.json, wcag-contrast-ratio e colorbrew"
        )
    }

    voci_data = []
    for idx, item in enumerate(data.get("voci", [])):
        ref = item.get("riferimento") or item.get("ref", "")
        std = lookup_normative_entry(ref)
        v_id = item.get("id") or f"V-{idx+1:02d}"
        item = dict(item, id=v_id)

        # Misure reali: contrasto e target vengono calcolati qui, non letti dal modello.
        meas = apply_measurements(item, is_violation=True)
        if meas:
            item["descrizione"] = meas["descrizione"]
            item["correzione"] = meas["correzione"]
            item["affidabilita"] = meas["affidabilita"]
            item["motivo"] = meas["motivo"]
            for w in meas["avvisi"]:
                print(f"[checker] AVVISO {w}", file=sys.stderr)
        elif ref and any(k in ref for k in ("1.4.3", "1.4.6", "1.4.11", "2.5.5", "2.5.8")):
            print(f"[checker] AVVISO {v_id}: {ref} senza 'misure' nel payload: il valore NON è stato misurato dallo script.",
                  file=sys.stderr)
        elem = item.get("elemento", "")
        ambito = item.get("ambito") or std.get("ambito") or evaluate_ambito(ref)
        stato = item.get("stato") or std.get("stato") or evaluate_stato(ref)
        desc = item.get("descrizione") or item.get("nota") or std.get("nome", "")
        corr = item.get("correzione") or item.get("azione", "")
        dove = item.get("dove_si_corregge") or item.get("dove") or evaluate_dove_si_corregge(ref, desc, corr)
        sugg_ann = item.get("suggerimento_annotazione") or evaluate_suggerimento_annotazione(
            ref, elem, desc, corr, bool(item.get("annotazione_presente", False))
        )
        gravita = normalize_gravita(item.get("gravita", "Moderata"))
        affidabilita = item.get("affidabilita", "Alta")

        # Arricchisce il riferimento con il livello ufficiale se mancante (es. 'WCAG 1.4.3' -> 'WCAG 1.4.3 (AA)')
        if std.get("level") and "(" not in ref:
            ref = f"WCAG {std['num']} ({std['level']})"

        voci_data.append({
            "id": v_id,
            "pagina": item.get("pagina", ""),
            "elemento": elem,
            "nodo_id": item.get("nodo_id") or item.get("node_id") or "",
            "ambito": ambito,
            "riferimento": ref,
            "descrizione": desc,
            "gravita": gravita,
            "stato": stato,
            "affidabilita": affidabilita,
            "motivo": item.get("motivo", ""),
            "conflitto": item.get("conflitto", "No"),
            "motivo_conflitto": item.get("motivo_conflitto", ""),
            "correzione": corr,
            "dove_si_corregge": dove,
            "suggerimento_annotazione": sugg_ann,
            "fonte": item.get("fonte", "Agente di audit")
        })

    corretto_data = []
    for item in data.get("corretto", []):
        ref = item.get("riferimento") or item.get("ref", "")
        ambito = item.get("ambito") or evaluate_ambito(ref)
        meas = apply_measurements(item, is_violation=False)
        if meas:
            for w in meas["avvisi"]:
                print(f"[checker] AVVISO {w}", file=sys.stderr)
        corretto_data.append({
            "ambito": ambito,
            "pagina": item.get("pagina", ""),
            "elemento": item.get("elemento", ""),
            "descrizione": meas["descrizione"] if meas else item.get("descrizione", ""),
            "riferimento": ref
        })

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    return compile_audit_report(template_path, output_path, session_data, voci_data, corretto_data)


def figma_folder_name(session: Dict[str, Any]) -> str:
    """Nome cartella di output = nome del file Figma analizzato (caratteri non validi rimossi)."""
    name = str(session.get("file_figma") or session.get("caso") or "Figma senza nome").strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name)
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return name or "Figma senza nome"


def resolve_output_path(session: Dict[str, Any], out_arg: Optional[str], out_root: Optional[str]) -> str:
    """
    Il report viene SEMPRE salvato in <out_root>/<nome file Figma>/<nome file>.xlsx.
    Se --out contiene già una cartella con il nome del Figma, viene rispettata.
    """
    folder = figma_folder_name(session)
    root = os.path.abspath(out_root or os.getcwd())
    if out_arg:
        filename = os.path.basename(out_arg)
        if not filename.lower().endswith(".xlsx"):
            filename += ".xlsx"
        parent = os.path.dirname(os.path.abspath(out_arg))
        if os.path.basename(parent) == folder:
            return os.path.join(parent, filename)
    else:
        filename = f"{folder}-{datetime.now().strftime('%Y-%m-%d')}-audit.xlsx"
    return os.path.join(root, folder, filename)


def main():
    parser = argparse.ArgumentParser(
        description="checker.py — Motore deterministico per l'Agente di Audit (W3C wcag.json + wcag-contrast-ratio + colorbrew)"
    )
    parser.add_argument("--demo", action="store_true", help="Esegue test dimostrativo librerie W3C e dizionario wcag.json")
    parser.add_argument("--template", default="Audit_modello.xlsx", help="Percorso del template Audit_modello.xlsx")
    parser.add_argument("--out", help="Nome del file Excel (.xlsx). Viene sempre salvato nella cartella con il nome del file Figma")
    parser.add_argument("--out-root", help="Cartella base in cui creare la cartella con il nome del Figma (default: cartella corrente)")
    parser.add_argument("--input-json", help="Percorso file JSON contenente {session, voci, corretto}")
    parser.add_argument("--stdin", action="store_true", help="Legge il payload JSON dallo standard input")

    args = parser.parse_args()

    if args.demo:
        print("=== Test Checker Universale (W3C wcag.json + wcag-contrast-ratio + colorbrew) ===")
        print(f"Criteri WCAG 2.2 caricati da references/wcag.json: {len(WCAG_CRITERIA)}")
        print(f"Euristiche di Nielsen caricate: {len(NIELSEN_HEURISTICS)}")
        c1 = check_contrast("#767676", "#FFFFFF")
        print(f"Testo #767676 su #FFFFFF -> Ratio: {c1['ratio']}:1 | Conforme AA: {c1['compliant']} | Engine: {c1['engine']}")
        sugg = evaluate_suggerimento_annotazione("WCAG 2.4.6", "Pulsante ricerca solo-icona")
        print(f"Suggerimento Annotazione Figma per pulsante solo-icona -> {sugg}")
        sys.exit(0)

    if args.input_json or args.stdin:
        if args.stdin:
            raw_data = json.load(sys.stdin)
        else:
            with open(args.input_json, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

        template_file = args.template
        if not os.path.exists(template_file):
            alt_template = os.path.join(os.path.dirname(__file__), "../../../Audit_modello.xlsx")
            if os.path.exists(alt_template):
                template_file = alt_template

        sess = raw_data.setdefault("session", {})
        final_out = resolve_output_path(sess, args.out, args.out_root)
        out_path = compile_from_json(template_file, final_out, raw_data)
        print(f"Report Excel compilato con successo: {out_path}")
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()


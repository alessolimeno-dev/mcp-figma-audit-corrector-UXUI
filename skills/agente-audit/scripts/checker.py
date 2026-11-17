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

import copy
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
        parse_measures_from_text,
    )
    from skills.common.lib.nodi_utils import (
        normalize_nodi,
        nodi_to_cell,
        formula_da_correggere,
        post_for_node,
        DECISIONI_APPROVATE,
        MAX_RIGHE_VOCI,
        COL_VOCI_DECISIONE,
        COL_VOCI_CHI_APPLICA,
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
        parse_measures_from_text,
    )
    from common.lib.nodi_utils import (  # type: ignore
        normalize_nodi,
        nodi_to_cell,
        formula_da_correggere,
        post_for_node,
        DECISIONI_APPROVATE,
        MAX_RIGHE_VOCI,
        COL_VOCI_DECISIONE,
        COL_VOCI_CHI_APPLICA,
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
# TIPO DI ELEMENTO UI (lista chiusa, generica: vale per qualsiasi progetto Figma)
# ==============================================================================
# Categoria funzionale del nodo, scelta dal modello. Serve a (1) scegliere il suggerimento di annotazione senza
# indovinare dalle parole del testo libero e (2) tenere separati nel raggruppamento elementi di natura diversa.
TIPI_ELEMENTO = (
    "immagine-informativa", "immagine-decorativa", "pulsante-solo-icona", "pulsante",
    "link", "campo-form", "titolo", "testo", "contenitore", "altro",
)
# Parola chiave che attiva l'affinamento in evaluate_suggerimento_annotazione (gli altri tipi non lo attivano)
_TIPO_ELEMENTO_KEYWORD = {
    "immagine-informativa": "immagine",
    "immagine-decorativa": "immagine decorativa",
    "pulsante-solo-icona": "solo-icona",
}


def normalize_tipo_elemento(tipo: Any) -> str:
    """Porta il tipo_elemento a un valore della lista chiusa ('' se mancante; 'altro' se non riconosciuto)."""
    t = re.sub(r"[\s_]+", "-", str(tipo or "").strip().lower())
    if not t:
        return ""
    return t if t in TIPI_ELEMENTO else "altro"


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
    annotazione_presente: bool = False,
    tipo_elemento: str = ""
) -> str:
    """
    Genera deterministicamente a 0 token il suggerimento per la nuova colonna
    'Suggerimento (Annotazioni in Figma)' attingendo dalle Tecniche W3C in references/wcag.json.
    Non impone il testo editoriale dell'aria-label o dell'alt, ma indica il codice/attributo da annotare.
    Se `tipo_elemento` (lista chiusa TIPI_ELEMENTO) è dichiarato, l'affinamento usa SOLO quello e non le parole
    chiave del testo libero; senza `tipo_elemento` vale l'euristica storica a parole chiave.
    """
    if annotazione_presente:
        return "Annotazione già presente in Figma"

    tipo = normalize_tipo_elemento(tipo_elemento)
    if tipo:
        el_low = _TIPO_ELEMENTO_KEYWORD.get(tipo, "")
    else:
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


COL_VOCI_TIPO_MOTIVO = "T"


def riepilogo_formule_corrette() -> Dict[str, str]:
    """
    Formule del foglio Riepilogo (conteggi di Decisione, Tipo di motivo, Chi applica) con l'intervallo di Voci.
    Nel template Audit_modello.xlsx sono scritte senza intervallo (`COUNTIF(Voci!:,A26)`) e non funzionano:
    qui si riscrivono sempre. Righe: 26-28 Decisione, 32-36 Rifiutate per tipo di motivo, 40-42 Chi applica.
    """
    n = MAX_RIGHE_VOCI
    dec = f"Voci!${COL_VOCI_DECISIONE}$2:${COL_VOCI_DECISIONE}${n}"
    tipo = f"Voci!${COL_VOCI_TIPO_MOTIVO}$2:${COL_VOCI_TIPO_MOTIVO}${n}"
    chi = f"Voci!${COL_VOCI_CHI_APPLICA}$2:${COL_VOCI_CHI_APPLICA}${n}"
    f: Dict[str, str] = {}
    for r in (26, 27, 28):
        f[f"B{r}"] = f"=COUNTIF({dec},A{r})"
    for r in range(32, 37):
        f[f"B{r}"] = f'=COUNTIFS({dec},"Rifiutata",{tipo},A{r})'
    for r in (40, 41, 42):
        f[f"B{r}"] = f"=COUNTIF({chi},A{r})"
    return f


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
    - Colonna D di Voci: elenco dei nodi della voce (uno per riga); foglio Nodi: una riga per coppia nodo-errore,
      con la formula 'Da correggere' calcolata da Decisione (R) e Chi applica (V) di Voci.
    Richiede openpyxl (nessun fallback): ogni voce di voci_data porta la lista normalizzata `nodi`.
    """
    if not HAS_OPENPYXL:
        raise SystemExit(
            "[checker] ERRORE: openpyxl non è installato. Usa l'ambiente locale del progetto "
            "(<ROOT>/.venv/bin/python) oppure installa le dipendenze: pip install -r requirements.txt"
        )
    shutil.copyfile(template_path, output_path)
    stats = calculate_riepilogo_stats(voci_data, session_data)

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
    s_voci.cell(1, 4, 'ID Nodi Figma (uno per riga)')
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
        s_voci.cell(r, 4, nodi_to_cell(item.get('nodi', [])))  # un ID nodo per riga
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

    # 3b. Compila Nodi: una riga per coppia nodo-errore (solo nodi con errore). 'Da correggere' è una formula
    #     che legge Decisione (R) e Chi applica (V) di Voci: si aggiorna da sola quando il progettista compila i menù.
    s_nodi = wb['Nodi']
    stile_riga = [copy.copy(s_nodi.cell(2, c)._style) for c in range(1, 7)]
    r = 2
    for item in voci_data:
        for n in item.get('nodi', []):
            valori = [n['id'], n['pagina'], n['tipo'], n['elemento'], item.get('id', ''), formula_da_correggere(r)]
            for c, val in enumerate(valori, start=1):
                cell = s_nodi.cell(r, c, val)
                cell._style = copy.copy(stile_riga[c - 1])
            r += 1
    wb.calculation.fullCalcOnLoad = True  # Excel ricalcola le formule all'apertura

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
    for coord, formula in riepilogo_formule_corrette().items():  # il template ha le formule senza intervallo (Voci!:)
        s_riep[coord] = formula

    wb.save(output_path)
    _inject_cached_values(output_path, {'Riepilogo': stats})
    return output_path


# ==============================================================================
# RAGGRUPPAMENTO DETERMINISTICO DELLE SEGNALAZIONI IN VOCI (errori comuni)
# ==============================================================================
_MISURABILI = ("1.4.3", "1.4.6", "1.4.11", "2.5.5", "2.5.8")
_GRAVITA_ORDINE = {"": 0, "Lieve": 1, "Moderata": 2, "Grave": 3, "Bloccante": 4}


def _norm_text(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _is_misurabile(ref: str) -> bool:
    return any(k in str(ref or "") for k in _MISURABILI)


def _misure_key(misure: Optional[Dict[str, Any]]) -> Optional[Tuple[Any, ...]]:
    """Chiave delle misure: i valori che determinano la correzione calcolata. None se mancano dati sufficienti."""
    m = misure or {}
    try:
        if m.get("fg") and m.get("bg"):
            return ("contrasto", str(m["fg"]).strip().upper(), str(m["bg"]).strip().upper(),
                    bool(m.get("testo_grande", False)), bool(m.get("componente_ui", False)))
        if m.get("w") is not None and m.get("h") is not None:
            return ("target", round(float(m["w"]), 2), round(float(m["h"]), 2),
                    None if m.get("min") is None else float(m["min"]))
    except (TypeError, ValueError):
        return None
    return None


def _group_key(item: Dict[str, Any], tipo: str, sugg: str, unique: int) -> Tuple[Any, ...]:
    """
    Chiave di raggruppamento. Regola di fondo: NEL DUBBIO SI DIVIDE (una voce in più costa una riga,
    una fusione sbagliata applicherebbe la stessa correzione a nodi che ne richiedono una diversa).
    - criteri misurabili (contrasto, target): riferimento + misure identiche (colori / dimensioni);
      senza misure non si raggruppa mai;
    - tutto il resto (criteri WCAG con annotazione, euristiche di Nielsen, ecc.): riferimento + tipo_elemento +
      suggerimento + descrizione identica.
    """
    ref = item.get("riferimento") or item.get("ref", "")
    ref_key = extract_wcag_num(ref) or _norm_text(ref)
    if _is_misurabile(ref):
        mk = _misure_key(item.get("misure"))
        return ("misura", ref_key, mk) if mk is not None else ("unica", unique)
    # Tutti i criteri non misurabili si uniscono solo con descrizione identica (confronto senza maiuscole e
    # punteggiatura): due difetti diversi dello stesso criterio (es. gerarchia dei titoli e landmark in 1.3.1)
    # hanno lo stesso suggerimento ma restano voci separate, così il progettista decide su ciascuno.
    desc_key = re.sub(r"[^\w\s]", "", _norm_text(item.get("descrizione") or item.get("nota")))
    return ("descrizione", ref_key, tipo, sugg or "", desc_key)


def _join_distinct(values: List[str], sep: str = "; ") -> str:
    seen: List[str] = []
    for v in values:
        v = str(v or "").strip()
        if v and v not in seen:
            seen.append(v)
    return sep.join(seen)


def group_voci(voci_in: List[Dict[str, Any]], warn=None) -> List[Dict[str, Any]]:
    """
    Unisce in una sola voce le segnalazioni che hanno lo stesso errore comune (vedi _group_key).
    Ogni segnalazione porta i suoi `nodi` (anche uno solo); la voce risultante li raccoglie tutti.
    Gli ID (V-01, V-02, ...) sono assegnati qui, in ordine di prima comparsa.
    """
    warn = warn or (lambda _m: None)
    gruppi: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for idx, raw in enumerate(voci_in):
        label = raw.get("id") or f"segnalazione {idx + 1}"
        elem = raw.get("elemento", "")
        ref = raw.get("riferimento") or raw.get("ref", "")
        tipo_in = raw.get("tipo_elemento", "")
        tipo = normalize_tipo_elemento(tipo_in)
        if tipo_in and str(tipo_in).strip().lower().replace(" ", "-").replace("_", "-") not in TIPI_ELEMENTO:
            warn(f"{label}: tipo_elemento '{tipo_in}' non valido (ammessi: {', '.join(TIPI_ELEMENTO)}); usato 'altro'")
        nodi = normalize_nodi(raw.get("nodi") or [], default_pagina=raw.get("pagina", ""),
                              default_elemento=elem, warn=lambda m, _l=label: warn(f"{_l}: {m}"))
        sugg = raw.get("suggerimento_annotazione") or evaluate_suggerimento_annotazione(
            ref, elem, raw.get("descrizione", ""), raw.get("correzione", ""),
            bool(raw.get("annotazione_presente", False)), tipo
        )
        key = _group_key(raw, tipo, sugg, idx)
        if key not in gruppi:
            g = dict(raw)
            g["tipo_elemento"] = tipo
            g["suggerimento_annotazione"] = sugg
            g["nodi"] = list(nodi)
            g["_descrizioni"] = [raw.get("descrizione") or raw.get("nota") or ""]
            g["_correzioni"] = [raw.get("correzione") or raw.get("azione") or ""]
            g["_gravita"] = [raw.get("gravita", "")]
            g["_affidabilita"] = [raw.get("affidabilita", "Alta")]
            g["_conflitti"] = [raw.get("conflitto", "No")]
            gruppi[key] = g
        else:
            g = gruppi[key]
            g["nodi"].extend(nodi)
            g["_descrizioni"].append(raw.get("descrizione") or raw.get("nota") or "")
            g["_correzioni"].append(raw.get("correzione") or raw.get("azione") or "")
            g["_gravita"].append(raw.get("gravita", ""))
            g["_affidabilita"].append(raw.get("affidabilita", "Alta"))
            g["_conflitti"].append(raw.get("conflitto", "No"))

    out: List[Dict[str, Any]] = []
    for n, g in enumerate(gruppi.values(), start=1):
        g["id"] = f"V-{n:02d}"
        g["nodi"] = normalize_nodi(g["nodi"], warn=lambda m, _i=g["id"]: warn(f"{_i}: {m}"))
        nomi = list(dict.fromkeys(x["elemento"] for x in g["nodi"] if x["elemento"]))
        tot = len(g["nodi"])
        if nomi:
            if len(nomi) == 1:
                g["elemento"] = nomi[0] + (f" ({tot} nodi)" if tot > 1 else "")
            else:
                altri = tot - 1
                g["elemento"] = nomi[0] + f" (+{altri} {'nodo' if altri == 1 else 'nodi'})"
        g["descrizione"] = _join_distinct(g.pop("_descrizioni"))
        g["correzione"] = _join_distinct(g.pop("_correzioni"))
        grav = [normalize_gravita(x) for x in g.pop("_gravita")]
        peggiore = max(grav, key=lambda x: _GRAVITA_ORDINE.get(x, 0)) if grav else ""
        if peggiore:
            g["gravita"] = peggiore
        else:
            g.pop("gravita", None)  # nessuna gravità dichiarata: vale il default di compile_from_json
        affid = list(dict.fromkeys(g.pop("_affidabilita")))
        g["affidabilita"] = affid[0] if len(affid) == 1 else "Da controllare"
        g["conflitto"] = "Sì" if any(str(c).strip().lower() in ("sì", "si", "yes", "true") for c in g.pop("_conflitti")) else "No"
        out.append(g)
    return out


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

    # Raggruppamento a 0 token: le segnalazioni con lo stesso errore comune diventano una sola voce con più nodi.
    segnalazioni = data.get("voci", [])
    voci_raggruppate = group_voci(
        segnalazioni, warn=lambda msg: print(f"[checker] AVVISO {msg}", file=sys.stderr)
    )
    print(f"[checker] Raggruppamento: {len(segnalazioni)} segnalazioni -> {len(voci_raggruppate)} voci "
          f"({sum(len(v['nodi']) for v in voci_raggruppate)} nodi)", file=sys.stderr)

    voci_data = []
    for idx, item in enumerate(voci_raggruppate):
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

        # Nodi della voce (componenti, istanze, nodi singoli): obbligatori, almeno uno.
        nodi = normalize_nodi(
            item.get("nodi") or [],
            default_pagina=item.get("pagina", ""),
            default_elemento=elem,
            warn=lambda msg, _v=v_id: print(f"[checker] AVVISO {_v}: {msg}", file=sys.stderr),
        )
        if not nodi:
            raise SystemExit(
                f"[checker] ERRORE {v_id}: la voce non ha 'nodi'. Ogni voce deve elencare almeno un nodo "
                f"{{\"id\", \"pagina\", \"tipo\"}} (tipo: Componente, Istanza, Nodo singolo)."
            )
        pagine = list(dict.fromkeys(n["pagina"] for n in nodi if n["pagina"]))

        voci_data.append({
            "id": v_id,
            "pagina": ", ".join(pagine),
            "elemento": elem,
            "nodi": nodi,
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


# ==============================================================================
# VERIFICA POST-CORREZIONE  (/audit [link-figma] [file-excel])
# Sola lettura su Figma. Claude rilegge i nodi e scrive solo un piccolo JSON di misure; confronto, esiti,
# testo della colonna "Differenza", fogli Verifica / Riepilogo / Sessione li scrive lo script (0 token).
# ==============================================================================
PREFISSO_NUOVE = "N"          # ID delle voci nuove: N-01, N-02, ... (le voci del primo audit restano V-xx)
_VC = {"id": 1, "pagina": 2, "elemento": 3, "ambito": 5, "rif": 6, "desc": 7, "grav": 8, "stato": 9, "aff": 10,
       "confl": 12, "corr": 14, "dove": 15, "sugg": 16, "dec": 18, "tipo_mot": 20, "chi": 22}
_LOG_OK = ("Risolto", "Annotato")   # esiti del Log Correzioni che escludono una "non risolta": se poi la misura è KO è una regressione
ESITI_VERIFICA = ("Confermata", "Regressione", "Non risolta", "Da verificare", "Non toccata", "Nuova")
_AMBITI = ("Usabilità", "Accessibilità")
_GRAVITA_COL = ("Lieve", "Moderata", "Grave", "Bloccante")


def _cella(ws, r: int, c: int) -> str:
    return str(ws.cell(r, c).value or "").strip()


def _approvata(decisione: Any) -> bool:
    """Una voce si rilegge se la decisione è Accolta/Modificata, a prescindere da chi applica (Agente, Entrambi, Progettista)."""
    return str(decisione or "").strip().lower() in {d.lower() for d in DECISIONI_APPROVATE}


def _norm_rif(ref: Any) -> str:
    return re.sub(r"\s*\(.*?\)", "", str(ref or "")).strip().lower()


def _n(x: Any) -> str:
    f = float(x)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _breve(m: Optional[Dict[str, Any]]) -> str:
    if not m:
        return ""
    return f"{m['ratio']}:1" if m["kind"] == "contrasto" else f"{_n(m['w'])}x{_n(m['h'])} px"


def _peggiore(ms: List[Dict[str, Any]]) -> Dict[str, Any]:
    return min(ms, key=lambda m: m["ratio"] if m["kind"] == "contrasto" else min(m["w"], m["h"]))


def leggi_report_verifica(excel_path: str) -> Dict[str, Any]:
    """Legge Voci, Nodi, Log Correzioni e Sessione del report (solo lettura, valori già calcolati)."""
    if not HAS_OPENPYXL:
        raise SystemExit("[checker] ERRORE: openpyxl non è installato. Usa <ROOT>/.venv/bin/python.")
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    for nome in ("Voci", "Nodi"):
        if nome not in wb.sheetnames:
            raise SystemExit(f"[checker] ERRORE: foglio '{nome}' non trovato in {excel_path}: serve un report generato da /audit.")
    wn = wb["Nodi"]
    nodi: Dict[str, List[Dict[str, str]]] = {}
    for r in range(2, wn.max_row + 1):
        nid, vid = _cella(wn, r, 1), _cella(wn, r, 5)
        if nid and vid:
            nodi.setdefault(vid, []).append({"id": nid, "pagina": _cella(wn, r, 2), "tipo": _cella(wn, r, 3),
                                             "elemento": _cella(wn, r, 4)})
    ws = wb["Voci"]
    voci: List[Dict[str, Any]] = []
    for r in range(2, ws.max_row + 1):
        vid = _cella(ws, r, _VC["id"])
        if not vid:
            continue
        v = {k: _cella(ws, r, c) for k, c in _VC.items()}
        v.update(
            id=vid, row=r, decisione=v.pop("dec"), chi=v.pop("chi"), tipo_motivo=v.pop("tipo_mot"),
            riferimento=v.pop("rif"), descrizione=v.pop("desc"), gravita=normalize_gravita(v.pop("grav")),
            nodi=normalize_nodi(nodi.get(vid, [])),
        )
        voci.append(v)
    log: Dict[str, Dict[str, str]] = {}
    if "Log Correzioni" in wb.sheetnames:
        wl = wb["Log Correzioni"]
        for r in range(2, wl.max_row + 1):
            vid = _cella(wl, r, 1)
            if vid:
                log[vid] = {"azione": _cella(wl, r, 6), "esito": _cella(wl, r, 8), "verifica": _cella(wl, r, 9)}
    sess = wb["Sessione"] if "Sessione" in wb.sheetnames else None
    sessione = {"file_figma": _cella(sess, 5, 2) if sess else "", "caso": _cella(sess, 4, 2) if sess else ""}
    return {"voci": voci, "log": log, "sessione": sessione}


def piano_verifica(voci: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(da rileggere, non toccate): non si rilegge solo ciò che il progettista ha rifiutato o lasciato senza decisione."""
    return [v for v in voci if _approvata(v["decisione"])], [v for v in voci if not _approvata(v["decisione"])]


def formatta_piano_verifica(da_leggere: List[Dict[str, Any]], non_toccate: List[Dict[str, Any]], log: Dict[str, Dict[str, str]]) -> str:
    righe = [f"Voci da rileggere su Figma: {len(da_leggere)} | non toccate (rifiutate o senza decisione, non rilette): {len(non_toccate)}"]
    pagine: List[str] = []
    for v in da_leggere:
        ref = v["riferimento"]
        esito_log = log.get(v["id"], {}).get("esito") or "nessuna riga nel Log"
        testa = f"{v['id']} [{ref}] {v['elemento']} - Log: {esito_log} - Chi applica: {v['chi'] or '-'}"
        if _is_misurabile(ref):
            cosa = "fg e bg (hex)" if "1.4." in ref else "w e h (px)"
            nodi = ", ".join(f"{n['id']} ({n['tipo']})" for n in v["nodi"]) or "(nessun nodo nel foglio Nodi)"
            righe.append(f"{testa}\n    leggere {cosa} di: {nodi}")
        else:  # annotazioni e criteri non misurabili: elenco compatto (gli ID dei nodi sono nel foglio Nodi)
            righe.append(f"{testa}\n    {len(v['nodi'])} nodi: annotazione (labelMarkdown) da rileggere solo se uno strumento di lettura la restituisce; "
                         "altrimenti lasciare vuoto (esito Da verificare)")
        pagine += [n["pagina"] for n in v["nodi"] if n["pagina"]]
    if non_toccate:
        righe.append("Non toccate: " + ", ".join(f"{v['id']} ({v['decisione'] or 'senza decisione'})" for v in non_toccate))
    if pagine:
        righe.append("Pagine con nodi da rileggere (facoltativo: get_metadata dei frame per vedere se il layout è cambiato): "
                     + ", ".join(dict.fromkeys(pagine)))
    return "\n".join(righe)


def scheletro_misure_post(da_leggere: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Modello di misure-post.json con tutti i nodi da rileggere: Claude compila solo i valori (campi vuoti = non letto)."""
    out: Dict[str, Any] = {}
    for v in da_leggere:
        ref = v["riferimento"]
        if _is_misurabile(ref):
            campi = {"fg": "", "bg": ""} if "1.4." in ref else {"w": "", "h": ""}
            out[v["id"]] = {n["id"]: dict(campi) for n in v["nodi"]}
        else:
            # un solo campo per voce: vale per tutti i nodi (compilarlo solo se l'annotazione è stata riletta su tutti)
            out[v["id"]] = {"annotazione": ""}
    return out


def _misura_dal_log(ref: str, log_row: Optional[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    for riga in str((log_row or {}).get("verifica", "")).splitlines():
        if "Misurato dopo" in riga:
            p = parse_measures_from_text(riga, ref)
            return measure(ref, p) if p else None
    return None


def valuta_voce(v: Dict[str, Any], post_voce: Optional[Dict[str, Any]], log_row: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Esito della verifica di una voce approvata, calcolato dalle misure rilette (mai da testo scritto dal modello)."""
    ref = v["riferimento"]
    misurabile = _is_misurabile(ref)
    prima = parse_measures_from_text(v["descrizione"], ref) if misurabile else None
    stati: List[Tuple[Dict[str, str], str, Optional[Dict[str, Any]]]] = []
    for n in v["nodi"]:
        p = post_for_node(post_voce, n["id"])
        res = None
        if p.get("azione") == "non_trovato":
            stato = "non_trovato"
        elif misurabile:
            m = {k: p[k] for k in ("fg", "bg", "w", "h", "min") if p.get(k) not in (None, "")}
            if m:
                merged = dict(prima or {})
                merged.update(m)
                res = measure(ref, merged)
            stato = ("ok" if res["compliant"] else "ko") if res else "nd"
        else:
            testo = str(p.get("annotazione") or "").strip()
            stato = ("ok" if testo == v["sugg"].strip() else "ko") if testo else "nd"
        stati.append((n, stato, res))

    ko = [(n, r) for n, s, r in stati if s in ("ko", "non_trovato")]
    nd = [n for n, s, _ in stati if s == "nd"]
    ok = [(n, r) for n, s, r in stati if s == "ok"]
    log_esito = (log_row or {}).get("esito", "")
    if ko:
        esito = "Regressione" if log_esito in _LOG_OK else "Non risolta"
    elif nd:
        esito = "Da verificare"
    else:
        esito = "Confermata"

    # Colonna Differenza
    if misurabile:
        misure_ora = [r for _, s, r in stati if r]
        parti = []
        if prima:
            pm = measure(ref, prima)
            parti.append(f"Audit {_breve(pm)}") if pm else None
        lm = _misura_dal_log(ref, log_row)
        if lm:
            parti.append(f"Correzione {_breve(lm)}")
        if misure_ora:
            tot = len(misure_ora)
            parti.append(f"Ora {_breve(_peggiore(misure_ora))}" + (f" (peggiore di {tot} nodi)" if tot > 1 else ""))
        diff = " → ".join(parti) if parti else "Nessuna misura disponibile"
        dettagli = []
        for n, r in ko:
            dettagli.append(f"{n['id']} ({_breve(r)})" if r else f"{n['id']} (nodo non trovato)")
        if dettagli:
            diff += f" | {len(ko)}/{len(v['nodi'])} nodi non conformi: " + ", ".join(dettagli[:3]) + (" …" if len(dettagli) > 3 else "")
        if nd:
            diff += f" | {len(nd)} nodi non rilevati: " + ", ".join(n["id"] for n in nd[:3]) + (" …" if len(nd) > 3 else "")
    else:
        if ko:
            diff = "Annotazione diversa dalla colonna P o nodo non trovato su: " + ", ".join(n["id"] for n, _ in ko[:3])
        elif nd and not ok:
            diff = "Annotazione non riletta (sola lettura): vale l'esito del Log" + (f" ({log_esito})" if log_esito else "")
        elif nd:
            diff = f"Annotazione coincide con la colonna P su {len(ok)} nodi; {len(nd)} non riletti"
        else:
            diff = f"Annotazione coincide con la colonna P su {len(ok)} {'nodo' if len(ok) == 1 else 'nodi'}"

    esito_corr = log_esito or ("Non nel Log (progettista)" if v["chi"].lower() == "progettista" else "Non nel Log")
    return {"esito": esito, "regressione": "Sì" if esito == "Regressione" else "No", "differenza": diff, "esito_correzione": esito_corr}


def prepara_voci_nuove(payload: Any, voci_note: List[Dict[str, Any]], warn=None) -> List[Dict[str, Any]]:
    """
    Voci nuove da un payload nel formato dell'audit ({"voci": [...]}): si raggruppano come nell'audit, si scartano i nodi
    già noti (stessa coppia nodo + criterio presente in Voci) e le rimaste prendono ID N-01, N-02, ...
    """
    warn = warn or (lambda _m: None)
    if isinstance(payload, list):
        payload = {"voci": payload}
    noti = {(n["id"], _norm_rif(v["riferimento"])) for v in voci_note for n in v["nodi"]}
    out: List[Dict[str, Any]] = []
    scartate = 0
    for g in group_voci((payload or {}).get("voci", []), warn=warn):
        ref = g.get("riferimento") or g.get("ref", "")
        std = lookup_normative_entry(ref)
        if std.get("level") and "(" not in ref:
            ref = f"WCAG {std['num']} ({std['level']})"
        nuovi = [n for n in g["nodi"] if (n["id"], _norm_rif(ref)) not in noti]
        if not nuovi:
            scartate += 1
            continue
        meas = apply_measurements(dict(g), is_violation=True)
        desc = meas["descrizione"] if meas else (g.get("descrizione") or std.get("nome", ""))
        out.append({
            "riferimento": ref, "elemento": g.get("elemento", ""), "descrizione": desc, "nodi": nuovi,
            "ambito": g.get("ambito") or std.get("ambito") or evaluate_ambito(ref),
            "gravita": normalize_gravita(g.get("gravita") or "Moderata"),
        })
    for i, g in enumerate(out, start=1):
        g["id"] = f"{PREFISSO_NUOVE}-{i:02d}"
    if scartate:
        print(f"[checker] {scartate} segnalazioni del nuovo audit erano già nel report (stesso nodo e criterio): ignorate.", file=sys.stderr)
    return out


def _clona_foglio(src, dst) -> None:
    """Copia valori, stili, larghezze e celle unite di un foglio in un altro foglio (anche di un altro file)."""
    for row in src.iter_rows():
        for c in row:
            d = dst.cell(c.row, c.column, c.value)
            if c.has_style:
                d.font, d.border, d.fill = copy.copy(c.font), copy.copy(c.border), copy.copy(c.fill)
                d.number_format, d.protection, d.alignment = c.number_format, copy.copy(c.protection), copy.copy(c.alignment)
    for k, dim in src.column_dimensions.items():
        dst.column_dimensions[k].width = dim.width
    for k, dim in src.row_dimensions.items():
        if dim.height:
            dst.row_dimensions[k].height = dim.height
    for rng in src.merged_cells.ranges:
        dst.merge_cells(str(rng))


def _scrivi_riepilogo(wb, template_path: str, voci: List[Dict[str, Any]], righe: List[Dict[str, str]]) -> Dict[str, Any]:
    """Rigenera il foglio Riepilogo dal template (matrice del primo audit, calcolata da Voci) e aggiunge il blocco
    'A correzione effettuata' a destra (colonne H-O). Ritorna i valori da iniettare nelle formule (cache)."""
    pos = wb.sheetnames.index("Riepilogo") if "Riepilogo" in wb.sheetnames else len(wb.sheetnames)
    if "Riepilogo" in wb.sheetnames:
        wb.remove(wb["Riepilogo"])
    ws = wb.create_sheet("Riepilogo", pos)
    _clona_foglio(openpyxl.load_workbook(template_path)["Riepilogo"], ws)

    items = [{
        "id": v["id"], "riferimento": v["riferimento"], "elemento": v["elemento"], "descrizione": v["descrizione"],
        "correzione": v["corr"], "ambito": v["ambito"], "gravita": v["gravita"], "stato": v["stato"],
        "dove_si_corregge": v["dove"], "suggerimento_annotazione": v["sugg"], "affidabilita": v["aff"], "conflitto": v["confl"],
    } for v in voci]
    for i in items:
        i["ambito"] = i["ambito"] or evaluate_ambito(i["riferimento"])
    for coord, val in calculate_riepilogo_stats(items).items():
        ws[coord] = val
    for c, t in zip("BCDEF", ("Lieve", "Moderata", "Grave", "Bloccante", "Totale")):
        ws[f"{c}3"] = t
    for coord, formula in riepilogo_formule_corrette().items():
        ws[coord] = formula

    # --- blocco "A correzione effettuata"
    st_head, st_lab, st_val = (copy.copy(ws[x]._style) for x in ("A3", "A4", "B4"))
    wrap = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    def put(coord: str, val: Any, st: Any) -> None:
        ws[coord].value = val
        ws[coord]._style = copy.copy(st)
        if st is st_val:
            ws[coord].alignment = wrap

    def fmt(ids: List[str]) -> str:
        return f"{', '.join(ids)} ({len(ids)})" if ids else "- (0)"

    per_amb: Dict[Tuple[str, str], List[str]] = {}
    aperte: Dict[Tuple[str, str], List[str]] = {}
    for r in righe:
        per_amb.setdefault((r["ambito"], r["esito"]), []).append(r["id"])
        if r["esito"] != "Confermata":
            aperte.setdefault((r["ambito"], r["gravita"]), []).append(r["id"])

    put("H3", "A correzione effettuata (verifica post-correzione)", st_head)
    for col, t in zip("HIJKLMNO", ("Ambito",) + ESITI_VERIFICA + ("Totale",)):
        put(f"{col}4", t, st_head)
    for i, amb in enumerate(_AMBITI, start=5):
        put(f"H{i}", amb, st_lab)
        for col, esito in zip("IJKLMN", ESITI_VERIFICA):
            put(f"{col}{i}", fmt(per_amb.get((amb, esito), [])), st_val)
        put(f"O{i}", sum(len(per_amb.get((amb, e), [])) for e in ESITI_VERIFICA), st_val)
    put("H7", "Totale", st_lab)
    for col, esito in zip("IJKLMN", ESITI_VERIFICA):
        put(f"{col}7", fmt([x for a in _AMBITI for x in per_amb.get((a, esito), [])]), st_val)
    put("O7", len(righe), st_val)

    put("H9", "Voci non confermate (ancora aperte) per gravità", st_head)
    for col, t in zip("HIJKLM", ("Ambito",) + _GRAVITA_COL + ("Totale",)):
        put(f"{col}10", t, st_head)
    for i, amb in enumerate(_AMBITI, start=11):
        put(f"H{i}", amb, st_lab)
        for col, g in zip("IJKL", _GRAVITA_COL):
            put(f"{col}{i}", fmt(aperte.get((amb, g), [])), st_val)
        put(f"M{i}", sum(len(aperte.get((amb, g), [])) for g in _GRAVITA_COL), st_val)
    put("H13", "Totale", st_lab)
    for col, g in zip("IJKL", _GRAVITA_COL):
        put(f"{col}13", fmt([x for a in _AMBITI for x in aperte.get((a, g), [])]), st_val)
    put("M13", sum(len(x) for x in aperte.values()), st_val)
    put("H15", "Ancora aperte = tutte le voci tranne le Confermate (Regressioni, Non risolte, Da verificare, Non toccate, Nuove). "
               "Regressione = la correzione risultava riuscita nel Log ma ora la misura non è conforme.", st_lab)
    ws["H15"].alignment = wrap
    ws.merge_cells("H15:O16")
    for col, w in zip("HIJKLMNO", (16, 24, 24, 24, 24, 24, 24, 10)):
        ws.column_dimensions[col].width = w

    # cache dei valori delle formule (conteggi di Decisione, Tipo di motivo, Chi applica)
    cache: Dict[str, int] = {}
    low = lambda s: str(s or "").strip().lower()
    for r in (26, 27, 28):
        cache[f"B{r}"] = sum(1 for v in voci if low(v["decisione"]) == low(ws[f"A{r}"].value))
    for r in range(32, 37):
        cache[f"B{r}"] = sum(1 for v in voci if low(v["decisione"]) == "rifiutata" and low(v["tipo_motivo"]) == low(ws[f"A{r}"].value))
    for r in (40, 41, 42):
        cache[f"B{r}"] = sum(1 for v in voci if low(v["chi"]) == low(ws[f"A{r}"].value))
    return cache


def verifica_report(
    excel_path: str,
    out_path: str,
    template_path: str,
    post: Optional[Dict[str, Any]] = None,
    nuove: Any = None,
) -> Dict[str, Any]:
    """Confronta il report con la rilettura di Figma e scrive la copia '-verifica.xlsx' (Log Correzioni in sola lettura)."""
    rep = leggi_report_verifica(excel_path)
    voci, log = rep["voci"], rep["log"]
    da_leggere, _ = piano_verifica(voci)
    ids_da_leggere = {v["id"] for v in da_leggere}
    post = post or {}
    if not post and da_leggere:
        print("[checker] AVVISO: nessuna misura rilette (--misure-post mancante o vuoto): le voci approvate risultano 'Da verificare'.",
              file=sys.stderr)

    righe: List[Dict[str, str]] = []
    for v in voci:
        ambito = v["ambito"] or evaluate_ambito(v["riferimento"])
        if v["id"] in ids_da_leggere:
            r = valuta_voce(v, post.get(v["id"]), log.get(v["id"]))
        else:
            motivo = "Voce rifiutata" if v["decisione"].lower() == "rifiutata" else "Voce senza decisione"
            r = {"esito": "Non toccata", "regressione": "No", "esito_correzione": "Nessuna",
                 "differenza": f"{motivo}: nessuna correzione richiesta, errore invariato (non riletto su Figma)."}
        righe.append(dict(r, id=v["id"], ambito=ambito, riferimento=v["riferimento"], gravita=v["gravita"], elemento=v["elemento"]))

    nuove_voci = prepara_voci_nuove(nuove, voci, warn=lambda m: print(f"[checker] AVVISO {m}", file=sys.stderr)) if nuove else []
    righe_nuove = [{
        "id": g["id"], "ambito": g["ambito"], "riferimento": g["riferimento"], "gravita": g["gravita"], "elemento": g["elemento"],
        "esito_correzione": "-", "esito": "Nuova", "regressione": "No",
        "differenza": g["descrizione"] + f" | {len(g['nodi'])} nodi: " + ", ".join(n["id"] for n in g["nodi"][:3]) + (" …" if len(g["nodi"]) > 3 else ""),
    } for g in nuove_voci]
    tutte = righe_nuove + righe   # le nuove (N-xx) in cima, poi le V-xx nell'ordine del primo audit

    wb = openpyxl.load_workbook(excel_path)
    # Sessione: versione di verifica e data (la riga v0 resta)
    if "Sessione" in wb.sheetnames:
        s = wb["Sessione"]
        for r, (lab, val) in zip((14, 15), (("Verifica post-correzione", "v1 (post-correzione)"),
                                            ("Data e ora della verifica", datetime.now().isoformat(timespec="seconds")))):
            s.cell(r, 1, lab)
            s.cell(r, 2, val)
            for c in (1, 2):
                s.cell(r, c)._style = copy.copy(s.cell(13, c)._style)
    # Foglio Verifica (ricreato a ogni esecuzione)
    if "Verifica" in wb.sheetnames:
        wb.remove(wb["Verifica"])
    wv = wb.create_sheet("Verifica")
    head = ["ID", "Ambito", "Normativa di riferimento", "Gravità", "Elemento", "Esito correzione (dal Log)",
            "Esito verifica", "Regressione", "Differenza"]
    wv.append(head)
    st_head = copy.copy(wb["Voci"].cell(1, 1)._style)
    for c in wv[1]:
        c._style = copy.copy(st_head)
        c.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="center")
    wrap = openpyxl.styles.Alignment(wrap_text=True, vertical="top")
    fill = {"Regressione": "F4B6B6", "Non risolta": "F8CBAD", "Nuova": "FFE699", "Da verificare": "DDEBF7", "Confermata": "C6E0B4"}
    for r in tutte:
        wv.append([r["id"], r["ambito"], r["riferimento"], r["gravita"], r["elemento"], r["esito_correzione"],
                   r["esito"], r["regressione"], r["differenza"]])
        for c in wv[wv.max_row]:
            c.alignment = wrap
        if r["esito"] in fill:
            wv.cell(wv.max_row, 7).fill = openpyxl.styles.PatternFill("solid", fgColor=fill[r["esito"]])
        if r["regressione"] == "Sì":
            wv.cell(wv.max_row, 8).fill = openpyxl.styles.PatternFill("solid", fgColor=fill["Regressione"])
    for col, w in zip("ABCDEFGHI", (8, 15, 22, 12, 36, 22, 16, 13, 80)):
        wv.column_dimensions[col].width = w
    wv.freeze_panes = "A2"
    wv.auto_filter.ref = f"A1:I{wv.max_row}"

    # Riepilogo: matrice del primo audit (da Voci) + blocco "A correzione effettuata"
    cache = _scrivi_riepilogo(wb, template_path, voci, tutte)
    wb.calculation.fullCalcOnLoad = True
    wb.save(out_path)
    _inject_cached_values(out_path, {"Riepilogo": cache})

    conteggi = {e: sum(1 for r in tutte if r["esito"] == e) for e in ESITI_VERIFICA}
    return {"out": out_path, "conteggi": conteggi, "righe": tutte}


def main_verifica(args, template_file: str) -> int:
    rep = leggi_report_verifica(args.excel)
    da_leggere, non_toccate = piano_verifica(rep["voci"])
    if args.plan:
        print(formatta_piano_verifica(da_leggere, non_toccate, rep["log"]))
        if args.plan_out:
            with open(args.plan_out, "w", encoding="utf-8") as f:
                json.dump(scheletro_misure_post(da_leggere), f, ensure_ascii=False, indent=1)
            print(f"\nModello delle misure da compilare: {args.plan_out}")
        return 0
    post, nuove = {}, None
    if args.misure_post:
        with open(args.misure_post, "r", encoding="utf-8") as f:
            post = json.load(f)
    if args.nuove:
        with open(args.nuove, "r", encoding="utf-8") as f:
            nuove = json.load(f)
    if args.out:
        out = args.out if os.path.dirname(args.out) else os.path.join(os.path.dirname(os.path.abspath(args.excel)), args.out)
    else:
        nome = figma_folder_name(rep["sessione"])
        out = os.path.join(os.path.dirname(os.path.abspath(args.excel)), f"{nome}-{datetime.now().strftime('%Y-%m-%d')}-verifica.xlsx")
    if os.path.abspath(out) == os.path.abspath(args.excel):
        raise SystemExit("[checker] ERRORE: --out coincide con il report di partenza: la verifica scrive sempre una copia.")
    res = verifica_report(args.excel, out, template_file, post, nuove)
    print(f"Verifica post-correzione scritta: {res['out']}")
    print("Esiti: " + ", ".join(f"{e} {n}" for e, n in res["conteggi"].items()))
    for r in res["righe"]:
        if r["esito"] in ("Regressione", "Non risolta", "Nuova"):
            print(f"  ATTENZIONE {r['id']} [{r['riferimento']}] {r['esito']}: {r['differenza']}")
    return 0


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
    # Verifica post-correzione (/audit [link] [file-excel])
    parser.add_argument("--verifica", action="store_true",
                        help="Verifica post-correzione: confronta il report Excel (--excel) con le misure rilette da Figma e scrive una copia '-verifica.xlsx'")
    parser.add_argument("--excel", help="Con --verifica: report Excel con decisioni e Log Correzioni (non viene modificato)")
    parser.add_argument("--plan", action="store_true", help="Con --verifica: elenca i nodi da rileggere su Figma, senza scrivere nulla")
    parser.add_argument("--plan-out", help="Con --verifica --plan: salva il modello di misure-post.json da compilare")
    parser.add_argument("--misure-post", help="Con --verifica: JSON {ID voce: {ID nodo: {fg,bg | w,h | annotazione}}} con i valori riletti da Figma")
    parser.add_argument("--nuove", help="Con --verifica: JSON {voci:[...]} nel formato dell'audit con gli errori nuovi trovati (ID N-01, N-02, ...)")

    args = parser.parse_args()

    if args.verifica:
        if not args.excel:
            parser.error("--verifica richiede --excel <report.xlsx>")
        template_file = args.template
        if not os.path.exists(template_file):
            alt_template = os.path.join(os.path.dirname(__file__), "../../../Audit_modello.xlsx")
            if os.path.exists(alt_template):
                template_file = alt_template
        sys.exit(main_verifica(args, template_file))

    if args.demo:
        print("=== Test Checker Universale (W3C wcag.json + wcag-contrast-ratio + colorbrew) ===")
        print(f"Criteri WCAG 2.2 caricati da references/wcag.json: {len(WCAG_CRITERIA)}")
        print(f"Euristiche di Nielsen caricate: {len(NIELSEN_HEURISTICS)}")
        c1 = check_contrast("#767676", "#FFFFFF")
        print(f"Testo #767676 su #FFFFFF -> Ratio: {c1['ratio']}:1 | Conforme AA: {c1['compliant']} | Engine: {c1['engine']}")
        sugg = evaluate_suggerimento_annotazione("WCAG 2.4.6", "Pulsante ricerca solo-icona")
        print(f"Suggerimento Annotazione Figma per pulsante solo-icona -> {sugg}")

        # Raggruppamento di esempio (dati inventati, nessun file letto o scritto)
        esempio = [
            {"elemento": "Bottone", "tipo_elemento": "pulsante", "riferimento": "WCAG 1.4.3 (AA)", "descrizione": "Contrasto insufficiente",
             "misure": {"fg": "#888888", "bg": "#FFFFFF"}, "nodi": [{"id": "<id-componente>", "pagina": "Pagina A", "tipo": "Componente"}]},
            {"elemento": "Bottone", "tipo_elemento": "pulsante", "riferimento": "WCAG 1.4.3 (AA)", "descrizione": "Contrasto insufficiente",
             "misure": {"fg": "#888888", "bg": "#FFFFFF"}, "nodi": [{"id": "I<id-istanza>;<id-nodo>", "pagina": "Pagina B"}]},
            {"elemento": "Bottone secondario", "tipo_elemento": "pulsante", "riferimento": "WCAG 1.4.3 (AA)", "descrizione": "Contrasto insufficiente",
             "misure": {"fg": "#777777", "bg": "#EEEEEE"}, "nodi": [{"id": "<id-nodo-2>", "pagina": "Pagina A"}]},
            {"elemento": "Foto", "tipo_elemento": "immagine-informativa", "riferimento": "WCAG 1.1.1 (A)", "descrizione": "Manca il testo alternativo",
             "nodi": [{"id": "<id-nodo-3>", "pagina": "Pagina A"}]},
        ]
        gruppi = group_voci(esempio)
        print(f"Raggruppamento di esempio: {len(esempio)} segnalazioni -> {len(gruppi)} voci (stessi colori uniti, colori diversi separati)")
        for g in gruppi:
            print(f"  {g['id']} {g['riferimento']}: nodi {[n['id'] + ' (' + n['tipo'] + ')' for n in g['nodi']]}")
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


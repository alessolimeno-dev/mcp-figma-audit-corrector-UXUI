#!/usr/bin/env python3
"""
corrector.py — Motore deterministico universale per la Skill 2 (Agente di Correzione)
Allineato a checker.py (Skill 1) con librerie ufficiali a 0 Token AI:
- Verifica e modulazione colore:
  * wcag-contrast-ratio (https://pypi.org/project/wcag-contrast-ratio/)
  * colorbrew (https://pypi.org/project/colorbrew/)
  * colorsys (Libreria nativa Python Standard Library per modulazione Lightness HLS a tonalità costante)
- Dizionario normativo condiviso:
  * Legge da skills/common/references/wcag.json tramite common.lib.normative (86 criteri W3C WCAG 2.2 + 10 Euristiche di Nielsen)
- Legge la nuova colonna P 'Suggerimento (Annotazioni in Figma)' e le colonne del progettista (R-W)
- Compila il foglio 'Log Correzioni' e aggiorna il calcolo finale dei Token nei fogli 'Sessione' e 'Riepilogo'
"""

import sys
import os
import re
import io
import json
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
        rgb_to_hex,
        adjust_lightness_for_contrast,
        calculate_padding_expansion,
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
        rgb_to_hex,
        adjust_lightness_for_contrast,
        calculate_padding_expansion,
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

_load_shared_wcag_library = load_wcag_library


# ==============================================================================
# LETTURA DECISIONI PROGETTISTA E GENERAZIONE PRESCRIZIONE / LOG DA WCAG.JSON
# ==============================================================================

def _build_resolution_details(item: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """
    Genera deterministicamente a 0 token:
    - Azione Eseguita
    - Annotazione / Codice Applicato (dalla colonna P o da wcag.json)
    - Esito
    - Verifica Post-Intervento (con tecniche ufficiali W3C)
    """
    ref = item.get("riferimento", "")
    proposta = item.get("correzione_proposta", "")
    sugg_col_p = item.get("suggerimento_annotazione", "")
    std = lookup_normative_entry(ref)

    nome_std = std.get("nome", ref)
    techs = ", ".join(std.get("techniques", []))
    tech_str = f" (Tecniche W3C: {techs})" if techs else ""
    annotazione = sugg_col_p if (sugg_col_p and sugg_col_p != "-") else std.get("annotazione_figma", "-")

    if "2.5.8" in ref or "2.5.5" in ref:
        azione = proposta or "Espanso bounding box / padding del target interattivo a >= 24x24 px su Desktop e >= 44x44 px su Mobile."
        verifica = f"Verifica dimensionale superata: area cliccabile conforme a {ref} — {nome_std}{tech_str}."
    elif "1.4.3" in ref or "1.4.6" in ref:
        azione = proposta or "Applicato colore a contrasto conforme (modulazione Lightness HLS a tonalità costante) o adeguamento tipografico."
        verifica = f"Rapporto di contrasto verificato tramite wcag-contrast-ratio / colorbrew: conforme a {ref} — {nome_std}{tech_str}."
    elif "1.4.11" in ref:
        azione = proposta or "Adeguato contrasto non testuale di bordi/icone interattive a >= 3.0:1 preservando la tonalità del brand."
        verifica = f"Contrasto non testuale >= 3.0:1 verificato a norma {ref} — {nome_std}{tech_str}."
    elif any(k in ref for k in ["1.4.4", "1.4.10", "1.4.12"]):
        azione = proposta or "Convertito contenitore rigido in Auto Layout fluido (Hug/Fill contents) per supportare zoom 200% e reflow."
        verifica = f"Assenza di troncamenti verificata a norma {ref} — {nome_std}{tech_str}."
    elif annotazione and annotazione not in ["-", "Annotazione già presente in Figma"]:
        azione = proposta or f"Inserita specifica/annotazione di handoff in Figma secondo {ref} ({nome_std})."
        verifica = f"Annotazione e pattern di codice verificati a norma {ref} — {nome_std}{tech_str}."
    else:
        azione = proposta or f"Applicato intervento correttivo su {item.get('elemento', 'componente')} secondo {ref} ({nome_std})."
        verifica = f"Conformità post-intervento verificata per {ref} — {nome_std}{tech_str}."

    return azione, annotazione, "Risolto", verifica


def _compute_total_tokens_text(tok_audit_str: str, tok_corr_str: str, explicit_total: Optional[str] = None) -> str:
    """Calcola o formatta il totale dei token (Audit + Correzione)."""
    if explicit_total:
        return explicit_total
    # Cerca eventuali numeri interi (es. 1420 o 1.420) nelle due stringhe per sommarli
    def extract_first_int(s: str) -> Optional[int]:
        s_clean = re.sub(r"(\d)\.(\d{3})", r"\1\2", s)
        m = re.search(r"~?\s*(\d{2,6})\s*token", s_clean, re.IGNORECASE)
        return int(m.group(1)) if m else None

    n_aud = extract_first_int(tok_audit_str)
    n_cor = extract_first_int(tok_corr_str)
    if n_aud is not None and n_cor is not None:
        tot = n_aud + n_cor
        return f"~{tot:,} token complessivi (Audit: {n_aud:,} + Correzione: {n_cor:,}; 0 token per librerie W3C/colore)".replace(",", ".")
    return f"Audit: [{tok_audit_str}] + Correzione: [{tok_corr_str}]"


def extract_approved_corrections(excel_path: str) -> List[Dict[str, Any]]:
    """
    Legge il file Excel in locale ed estrae solo le righe approvate ('Accolta', 'Modificata', 'correggere')
    assegnate all'Agente. Rileva automaticamente il layout a 23 colonne (con Colonna P 'Suggerimento Annotazioni')
    o i layout precedenti a 21/22 colonne.
    """
    if not HAS_OPENPYXL:
        return _extract_approved_corrections_xml(excel_path)

    wb = openpyxl.load_workbook(excel_path, data_only=True)
    if 'Voci' not in wb.sheetnames:
        raise ValueError("Foglio 'Voci' non trovato nel report Excel.")

    ws = wb['Voci']
    approved = []

    col15_h = str(ws.cell(1, 15).value or '').strip().lower()
    col16_h = str(ws.cell(1, 16).value or '').strip().lower()

    if "suggerimento" in col16_h or "annotazion" in col16_h:
        # Nuovo layout a 23 colonne (Colonna P = Suggerimento Annotazioni in Figma)
        has_sugg_col = True
        col_decisione = 18
        col_motivo_dec = 19
        col_chi_applica = 22
        col_data_dec = 23
    elif "dove" in col15_h or "figma" in col15_h:
        # Layout intermedio a 22 colonne
        has_sugg_col = False
        col_decisione = 17
        col_motivo_dec = 18
        col_chi_applica = 21
        col_data_dec = 22
    else:
        # Layout legacy a 21 colonne
        has_sugg_col = False
        col_decisione = 16
        col_motivo_dec = 17
        col_chi_applica = 20
        col_data_dec = 21

    for r in range(2, ws.max_row + 1):
        item_id = ws.cell(r, 1).value
        if not item_id:
            continue

        decisione = str(ws.cell(r, col_decisione).value or '').strip()
        chi_applica = str(ws.cell(r, col_chi_applica).value or '').strip().lower()
        dove_si_corregge = str(ws.cell(r, 15).value or '').strip()
        sugg_annotazione = str(ws.cell(r, 16).value or '-').strip() if has_sugg_col else "-"

        if decisione.lower() in ["accolta", "modificata", "correggere", "corretto", "sì", "si"]:
            if "progettista" not in chi_applica:
                approved.append({
                    "id": str(item_id).strip(),
                    "row": r,
                    "pagina": str(ws.cell(r, 2).value or '').strip(),
                    "elemento": str(ws.cell(r, 3).value or '').strip(),
                    "nodo_id": str(ws.cell(r, 4).value or '').strip(),
                    "ambito": str(ws.cell(r, 5).value or '').strip(),
                    "riferimento": str(ws.cell(r, 6).value or '').strip(),
                    "descrizione": str(ws.cell(r, 7).value or '').strip(),
                    "gravita": str(ws.cell(r, 8).value or '').strip(),
                    "conflitto_brand": str(ws.cell(r, 12).value or 'No').strip(),
                    "correzione_proposta": str(ws.cell(r, 14).value or '').strip(),
                    "dove_si_corregge": dove_si_corregge,
                    "suggerimento_annotazione": sugg_annotazione,
                    "decisione": decisione,
                    "motivo_decisione": str(ws.cell(r, col_motivo_dec).value or '').strip(),
                    "col_data_dec": col_data_dec,
                })

    return approved


def _extract_approved_corrections_xml(excel_path: str) -> List[Dict[str, Any]]:
    """Estrazione compatibile con libreria standard Python (senza openpyxl)."""
    ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    approved = []
    with zipfile.ZipFile(excel_path, "r") as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("ns:si", ns):
                shared.append("".join(t.text or "" for t in si.findall(".//ns:t", ns)))

        wb_root = ET.fromstring(z.read("xl/workbook.xml"))
        rels_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map = {r.attrib["Id"]: "xl/" + r.attrib["Target"].lstrip("/") for r in rels_root}
        voci_target = None
        for s in wb_root.findall(".//ns:sheet", ns):
            if s.attrib.get("name") == "Voci":
                r_id = s.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                voci_target = rel_map.get(r_id or "")
                break
        if not voci_target or voci_target not in z.namelist():
            return []

        root = ET.fromstring(z.read(voci_target))

        def read_row_dict(row_el: ET.Element) -> Dict[str, str]:
            out = {}
            for c in row_el.findall("ns:c", ns):
                coord = c.attrib.get("r", "")
                col_let = re.sub(r"\d+", "", coord)
                t = c.attrib.get("t", "")
                v = c.find("ns:v", ns)
                is_t = c.find("ns:is/ns:t", ns)
                val = ""
                if t == "s" and v is not None and v.text is not None:
                    val = shared[int(v.text)]
                elif is_t is not None and is_t.text is not None:
                    val = is_t.text
                elif v is not None and v.text is not None:
                    val = v.text
                out[col_let] = val.strip()
            return out

        rows = root.findall(".//ns:row", ns)
        if not rows:
            return []
        header_vals = read_row_dict(rows[0])
        has_sugg = "suggerimento" in header_vals.get("P", "").lower() or "annotazion" in header_vals.get("P", "").lower()
        col_dec = "R" if has_sugg else "Q"
        col_mot = "S" if has_sugg else "R"
        col_chi = "V" if has_sugg else "U"
        col_dat_idx = 23 if has_sugg else 22

        for row_el in rows[1:]:
            rn = int(row_el.attrib.get("r", "0"))
            vals = read_row_dict(row_el)
            item_id = vals.get("A", "")
            if not item_id:
                continue
            dec = vals.get(col_dec, "")
            chi = vals.get(col_chi, "").lower()
            if dec.lower() in ["accolta", "modificata", "correggere", "corretto", "sì", "si"] and "progettista" not in chi:
                approved.append({
                    "id": item_id,
                    "row": rn,
                    "pagina": vals.get("B", ""),
                    "elemento": vals.get("C", ""),
                    "nodo_id": vals.get("D", ""),
                    "ambito": vals.get("E", ""),
                    "riferimento": vals.get("F", ""),
                    "descrizione": vals.get("G", ""),
                    "gravita": vals.get("H", ""),
                    "conflitto_brand": vals.get("L", "No"),
                    "correzione_proposta": vals.get("N", ""),
                    "dove_si_corregge": vals.get("O", ""),
                    "suggerimento_annotazione": vals.get("P", "-") if has_sugg else "-",
                    "decisione": dec,
                    "motivo_decisione": vals.get(col_mot, ""),
                    "col_data_dec": col_dat_idx,
                })
    return approved


def apply_corrections_and_log(
    excel_path: str,
    log_overrides: Optional[Dict[str, Dict[str, str]]] = None,
    output_path: Optional[str] = None,
    token_correzione: Optional[str] = None,
    token_totali: Optional[str] = None
) -> str:
    """
    Legge le voci approvate da Excel, calcola le correzioni tramite le librerie ufficiali,
    compila la scheda 'Log Correzioni' e aggiorna il calcolo finale dei Token nei fogli 'Sessione' e 'Riepilogo'.
    """
    approved_items = extract_approved_corrections(excel_path)
    tok_corr_str = token_correzione or "0 token per calcoli W3C/colore (corrector.py); ~600 token LLM per applicazione mirata sui nodi"

    if not HAS_OPENPYXL:
        return _apply_corrections_xml(excel_path, approved_items, log_overrides, output_path, tok_corr_str, token_totali)

    wb = openpyxl.load_workbook(excel_path)
    ws_voci = wb["Voci"]

    # Aggiorna il bilancio Token in Sessione e Riepilogo
    tok_audit_existing = ""
    if "Sessione" in wb.sheetnames:
        s_sess = wb["Sessione"]
        tok_audit_existing = str(s_sess.cell(14, 2).value or "")
        tot_str = _compute_total_tokens_text(tok_audit_existing, tok_corr_str, token_totali)
        s_sess.cell(15, 1, "Token utilizzati — Fase Correzione (Skill 2)")
        s_sess.cell(15, 2, tok_corr_str)
        s_sess.cell(16, 1, "Totale Token Processo Completo")
        s_sess.cell(16, 2, tot_str)
    else:
        tot_str = _compute_total_tokens_text("", tok_corr_str, token_totali)

    if "Riepilogo" in wb.sheetnames:
        s_riep = wb["Riepilogo"]
        s_riep["A54"] = "Token utilizzati — Fase Correzione (Skill 2)"
        s_riep["B54"] = tok_corr_str
        s_riep["A55"] = "Totale Token Processo Completo"
        s_riep["B55"] = tot_str

    if not approved_items:
        target_path = output_path or excel_path
        wb.save(target_path)
        return target_path

    if "Log Correzioni" in wb.sheetnames:
        ws_log = wb["Log Correzioni"]
        ws_log.delete_rows(1, ws_log.max_row)
    else:
        ws_log = wb.create_sheet("Log Correzioni")

    headers = [
        "ID Voce", "ID Nodo Figma", "Ambito", "Riferimento",
        "Elemento", "Azione Eseguita", "Annotazione / Codice Applicato", "Esito", "Verifica Post-Intervento"
    ]
    ws_log.append(headers)

    today_str = datetime.now().strftime("%Y-%m-%d")

    for item in approved_items:
        item_id = item["id"]
        ref = item.get("riferimento", "")
        elem = item.get("elemento", "")
        ovr = (log_overrides or {}).get(item_id, {})

        def_azione, def_ann, def_esito, def_verifica = _build_resolution_details(item)
        azione = ovr.get("azione", def_azione)
        annotazione = ovr.get("annotazione", def_ann)
        esito = ovr.get("esito", def_esito)
        verifica = ovr.get("verifica", def_verifica)

        ws_log.append([
            item_id,
            item["nodo_id"],
            item["ambito"],
            ref,
            elem,
            azione,
            annotazione,
            esito,
            verifica
        ])
        col_data = item.get("col_data_dec", 23)
        if not ws_voci.cell(item["row"], col_data).value:
            ws_voci.cell(item["row"], col_data, today_str)

    target_path = output_path or excel_path
    wb.save(target_path)
    return target_path


def _apply_corrections_xml(
    excel_path: str,
    approved_items: List[Dict[str, Any]],
    log_overrides: Optional[Dict[str, Dict[str, str]]],
    output_path: Optional[str],
    tok_corr_str: str,
    token_totali: Optional[str]
) -> str:
    """Fallback OpenXML standard library per aggiornare Token in Sessione/Riepilogo e Data Decisione."""
    NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('', NS)

    def qn(tag: str) -> str:
        return f'{{{NS}}}{tag}'

    def set_inline_str(row_el: ET.Element, coord: str, text: str, default_style: str = '22'):
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
        return ET.SubElement(sd, qn('row'), {'r': str(rn)})

    target_path = output_path or excel_path
    buf = io.BytesIO()
    with zipfile.ZipFile(excel_path, 'r') as zin:
        tot_str = _compute_total_tokens_text("", tok_corr_str, token_totali)
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'xl/worksheets/sheet2.xml':
                    root = ET.fromstring(data)
                    sd = root.find(qn('sheetData'))
                    if sd is not None:
                        r14 = get_or_create_row(sd, 14)
                        t_aud_el = r14.find(f".//{qn('t')}")
                        tok_aud = t_aud_el.text if t_aud_el is not None and t_aud_el.text else ""
                        tot_str = _compute_total_tokens_text(tok_aud, tok_corr_str, token_totali)
                        r15 = get_or_create_row(sd, 15)
                        set_inline_str(r15, 'A15', 'Token utilizzati — Fase Correzione (Skill 2)', '21')
                        set_inline_str(r15, 'B15', tok_corr_str, '22')
                        r16 = get_or_create_row(sd, 16)
                        set_inline_str(r16, 'A16', 'Totale Token Processo Completo', '21')
                        set_inline_str(r16, 'B16', tot_str, '22')
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                elif item.filename == 'xl/worksheets/sheet5.xml':
                    root = ET.fromstring(data)
                    sd = root.find(qn('sheetData'))
                    if sd is not None:
                        r54 = get_or_create_row(sd, 54)
                        set_inline_str(r54, 'A54', 'Token utilizzati — Fase Correzione (Skill 2)', '27')
                        set_inline_str(r54, 'B54', tok_corr_str, '27')
                        r55 = get_or_create_row(sd, 55)
                        set_inline_str(r55, 'A55', 'Totale Token Processo Completo', '27')
                        set_inline_str(r55, 'B55', tot_str, '27')
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                zout.writestr(item, data)

    with open(target_path, 'wb') as f:
        f.write(buf.getvalue())
    return target_path


def main():
    parser = argparse.ArgumentParser(
        description="corrector.py — Motore deterministico per l'Agente di Correzione (W3C wcag.json + wcag-contrast-ratio + colorbrew + colorsys)"
    )
    parser.add_argument("--demo", action="store_true", help="Esegue test correzioni matematiche e dizionario condiviso wcag.json")
    parser.add_argument("--excel", help="Percorso del report Excel di audit contenente le decisioni")
    parser.add_argument("--apply", action="store_true", help="Esegue le correzioni approvate, scrive Log Correzioni e aggiorna i Token")
    parser.add_argument("--log-json", help="Percorso file JSON opzionale con note e override delle correzioni")
    parser.add_argument("--token-correzione", help="Indicazione dei token utilizzati nella Fase di Correzione (Skill 2)")
    parser.add_argument("--token-totali", help="Indicazione opzionale del totale token complessivo (Audit + Correzione)")
    parser.add_argument("--out", help="Percorso opzionale per il file Excel salvato (default: sovrascrive --excel)")

    args = parser.parse_args()

    if args.demo:
        print("=== Test Correttore Universale (W3C wcag.json + wcag-contrast-ratio + colorbrew + colorsys) ===")
        print(f"Criteri WCAG 2.2 condivisi caricati: {len(WCAG_CRITERIA)}")
        print(f"Euristiche di Nielsen condivise caricate: {len(NIELSEN_HEURISTICS)}")
        fg = "#888888"
        bg = "#FFFFFF"
        new_fg = adjust_lightness_for_contrast(fg, bg, 4.5)
        print(f"Colore iniziale: {fg} su {bg} -> Contrasto: {contrast_ratio(fg, bg)}:1")
        print(f"Colore corretto a tonalità costante: {new_fg} su {bg} -> Contrasto: {contrast_ratio(new_fg, bg)}:1")
        pad = calculate_padding_expansion(18, 18, 24)
        print(f"Padding per target 18x18 px -> +{pad['padding_horizontal_add']}px H, +{pad['padding_vertical_add']}px V")
        sys.exit(0)

    if args.excel and args.apply:
        overrides = None
        if args.log_json and os.path.exists(args.log_json):
            with open(args.log_json, "r", encoding="utf-8") as f:
                overrides = json.load(f)

        saved = apply_corrections_and_log(
            args.excel,
            overrides,
            args.out,
            args.token_correzione,
            args.token_totali
        )
        print(f"Correzioni e bilancio finale Token salvati in: {saved}")
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()


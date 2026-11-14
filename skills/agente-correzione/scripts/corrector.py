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
- Compila il foglio 'Log Correzioni' e popola la Data della decisione nel foglio 'Voci'
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
    from skills.common.lib.wcag_checks import (
        measure,
        parse_measures_from_text,
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
    from common.lib.wcag_checks import (  # type: ignore
        measure,
        parse_measures_from_text,
    )

_load_shared_wcag_library = load_wcag_library

MEASURABLE_REFS = ("1.4.3", "1.4.6", "1.4.11", "2.5.5", "2.5.8")


def _is_measurable(ref: str) -> bool:
    return any(k in str(ref) for k in MEASURABLE_REFS)


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ==============================================================================
# PIANO DI CORREZIONE (dry-run): valori calcolati voce per voce, senza toccare nulla
# ==============================================================================

def build_correction_plan(
    items: List[Dict[str, Any]],
    measures_before: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Per ogni voce approvata calcola i valori da applicare su Figma (colore HLS a tonalità costante,
    padding per i target). Le misure "prima" vengono da `measures_before` (--misure-prima, lette da Figma)
    oppure dalla colonna Descrizione del report (scritta da checker.py). Se mancano, la voce risulta
    `misure_mancanti`: vanno lette da Figma con get_design_context e passate a --misure-prima.
    """
    plan = []
    for item in items:
        vid, ref = item["id"], item.get("riferimento", "")
        entry: Dict[str, Any] = {
            "id": vid, "nodo_id": item.get("nodo_id", ""), "riferimento": ref,
            "elemento": item.get("elemento", ""),
        }
        if not _is_measurable(ref):
            entry.update(kind="annotazione_o_altro", stato="non_misurabile",
                         nota="Nessun valore da calcolare: intervento/annotazione descritti in 'correzione_proposta'.",
                         correzione_proposta=item.get("correzione_proposta", ""))
            plan.append(entry)
            continue

        before = (measures_before or {}).get(vid) or parse_measures_from_text(item.get("descrizione", ""), ref)
        res = measure(ref, before) if before else None
        if not res:
            need = "fg e bg (hex)" if ("1.4." in ref) else "w e h (px)"
            entry.update(kind="contrasto" if "1.4." in ref else "target", stato="misure_mancanti",
                         nota=f"Misure non ricavabili dal report: leggere {need} del nodo da Figma e passarle in --misure-prima.")
        else:
            entry.update(res)
            entry["stato"] = "gia_conforme" if res["compliant"] else "da_correggere"
            if res["compliant"]:
                entry["nota"] = "La misura risulta già conforme: verificare con il progettista prima di modificare."
        plan.append(entry)
    return plan


def format_plan(plan: List[Dict[str, Any]]) -> str:
    """Rende il piano leggibile in chat (una riga per voce)."""
    lines = []
    for p in plan:
        head = f"{p['id']} [{p['riferimento']}] nodo {p['nodo_id'] or '?'} - {p['elemento']}"
        if p["stato"] == "da_correggere" and p["kind"] == "contrasto":
            lines.append(f"{head}\n    {p['testo']}\n    -> nuovo colore {p['suggerito_fg']} ({p['suggerito_ratio']}:1) "
                         f"HLS {p['hls_prima']} -> {p['hls_dopo']} | Figma rgb {p['figma_rgb_suggerito']}")
        elif p["stato"] == "da_correggere" and p["kind"] == "target":
            lines.append(f"{head}\n    {p['testo']}\n    -> +{p['padding_orizzontale_per_lato']:g}px H / +{p['padding_verticale_per_lato']:g}px V per lato "
                         f"=> {p['dimensione_finale'][0]:g}x{p['dimensione_finale'][1]:g} px")
        else:
            lines.append(f"{head}\n    {p['stato']}: {p.get('nota') or p.get('testo', '')}")
    return "\n".join(lines)


# ==============================================================================
# LETTURA DECISIONI PROGETTISTA E GENERAZIONE PRESCRIZIONE / LOG DA WCAG.JSON
# ==============================================================================

def _build_resolution_details(
    item: Dict[str, Any],
    post_measure: Optional[Dict[str, Any]] = None,
    before_measure: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, str, str]:
    """
    Restituisce (azione, annotazione, esito, verifica).

    La verifica NON è un testo generato: per i criteri misurabili (contrasto 1.4.3/1.4.6/1.4.11,
    target 2.5.5/2.5.8) è la misura post-intervento calcolata da wcag_checks.measure() sui valori
    riletti da Figma (`post_measure`). Senza misura l'esito è "Da verificare", mai "Risolto".
    Esiti: Risolto (misurato conforme) | Non risolto (misurato non conforme) | Annotato (solo
    annotazione per sviluppatori) | Da verificare (nessuna misura / non misurabile da script).
    """
    ref = item.get("riferimento", "")
    proposta = item.get("correzione_proposta", "")
    sugg_col_p = item.get("suggerimento_annotazione", "")
    std = lookup_normative_entry(ref)

    nome_std = std.get("nome", ref)
    techs = ", ".join(std.get("techniques", []))
    tech_str = f" (Tecniche W3C: {techs})" if techs else ""
    annotazione = sugg_col_p if (sugg_col_p and sugg_col_p != "-") else std.get("annotazione_figma", "-")
    ha_annotazione = bool(annotazione) and annotazione not in ["-", "Annotazione già presente in Figma"]

    if _is_measurable(ref):
        before = before_measure or parse_measures_from_text(item.get("descrizione", ""), ref) or {}
        res = None
        if post_measure:
            merged = dict(before)  # eredita testo_grande / componente_ui dalla misura "prima"
            merged.update(post_measure)
            res = measure(ref, merged)
        if res:
            if res["kind"] == "contrasto":
                prima = before.get("fg")
                azione = proposta or "Colore aggiornato su Figma."
                if prima and prima.upper() != res["fg"]:
                    azione = f"Colore aggiornato da {prima.upper()} a {res['fg']} (tonalità costante, modulazione Lightness HLS)."
            else:
                azione = proposta or "Dimensioni del target aggiornate su Figma."
                if before.get("w") is not None:
                    azione = f"Target portato da {before['w']:g}x{before['h']:g} a {res['w']:g}x{res['h']:g} px."
            esito = "Risolto" if res["compliant"] else "Non risolto"
            verifica = res["testo"].replace("Misurato:", "Misurato dopo l'intervento:", 1) + f" - {ref} - {nome_std}{tech_str}."
            return azione, annotazione, esito, verifica
        return (
            proposta or f"Intervento su {item.get('elemento', 'componente')} secondo {ref}.",
            annotazione,
            "Da verificare",
            f"Non misurata: nessuna misura post-intervento fornita (--misure-post) per {ref}.",
        )

    # Criteri non misurabili da script (annotazioni, Auto Layout/reflow, semantica...)
    azione = proposta or f"Applicato intervento correttivo su {item.get('elemento', 'componente')} secondo {ref} ({nome_std})."
    if ha_annotazione:
        return azione, annotazione, "Annotato", (
            f"Non misurabile da script: annotazione inserita secondo {ref} - {nome_std}{tech_str}. "
            "Controllo a cura del progettista."
        )
    return azione, annotazione, "Da verificare", (
        f"Non misurabile da script ({ref}): controllo visivo (screenshot) o revisione del progettista."
    )


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
    post_measures: Optional[Dict[str, Dict[str, Any]]] = None,
    before_measures: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """
    Legge le voci approvate da Excel e compila la scheda 'Log Correzioni' e la Data della decisione.

    NON modifica Figma e NON decide i valori: la modifica la fa Claude con use_figma (valori da
    --plan). Qui si registra l'esito: per contrasto e target la verifica è la misura calcolata sulle
    `post_measures` (valori riletti da Figma dopo la modifica); senza misura l'esito è "Da verificare".
    """
    approved_items = extract_approved_corrections(excel_path)
    post_measures = post_measures or {}
    before_measures = before_measures or {}

    if not HAS_OPENPYXL:
        raise RuntimeError("openpyxl non disponibile: usa l'interprete del progetto (<ROOT>/.venv/bin/python).")

    wb = openpyxl.load_workbook(excel_path)
    ws_voci = wb["Voci"]

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

        def_azione, def_ann, def_esito, def_verifica = _build_resolution_details(
            item, post_measures.get(item_id), before_measures.get(item_id)
        )
        azione = ovr.get("azione", def_azione)
        annotazione = ovr.get("annotazione", def_ann)
        if _is_measurable(ref):
            # Per i criteri misurabili esito e verifica li decide la misura, non un testo scritto a mano.
            if "esito" in ovr or "verifica" in ovr:
                print(f"[corrector] AVVISO {item_id}: override di esito/verifica ignorato ({ref} è misurabile: "
                      "usa --misure-post).", file=sys.stderr)
            esito, verifica = def_esito, def_verifica
        else:
            esito = ovr.get("esito", def_esito)
            verifica = ovr.get("verifica", def_verifica)
        if esito in ("Da verificare", "Non risolto"):
            print(f"[corrector] ATTENZIONE {item_id} [{ref}]: {esito} - {verifica}", file=sys.stderr)

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


def main():
    parser = argparse.ArgumentParser(
        description="corrector.py — Piano di correzione calcolato (--plan) e Log Correzioni con verifica misurata (--apply)"
    )
    parser.add_argument("--demo", action="store_true", help="Solo test delle formule (colore HLS, padding). NON legge l'Excel")
    parser.add_argument("--excel", help="Percorso del report Excel di audit contenente le decisioni")
    parser.add_argument("--plan", action="store_true",
                        help="Dry-run: legge l'Excel, elenca le voci approvate e calcola i valori da applicare su Figma. Non scrive nulla")
    parser.add_argument("--plan-out", help="Con --plan: salva anche il piano in JSON (valori colore/padding per voce)")
    parser.add_argument("--misure-prima", help="JSON {ID: {fg,bg | w,h}} con le misure lette da Figma PRIMA della modifica")
    parser.add_argument("--apply", action="store_true", help="Scrive il foglio Log Correzioni (verifica = misure post-intervento)")
    parser.add_argument("--misure-post", help="JSON {ID: {fg,bg | w,h}} con le misure rilette da Figma DOPO la modifica")
    parser.add_argument("--log-json", help="Percorso file JSON opzionale con note e override (azione, annotazione) delle correzioni")
    parser.add_argument("--out", help="Percorso opzionale per il file Excel salvato (default: sovrascrive --excel)")

    args = parser.parse_args()

    if args.demo:
        print("=== Test formule (NON legge l'Excel: per le voci reali usa --plan) ===")
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

    if args.excel and args.plan:
        items = extract_approved_corrections(args.excel)
        if not items:
            print("Nessuna voce approvata per l'Agente (Decisione Accolta/Modificata e Chi applica = Agente/Entrambi).")
            sys.exit(0)
        plan = build_correction_plan(items, _load_json(args.misure_prima))
        print(f"Voci approvate: {len(items)} (dry-run: nessun file modificato)\n")
        print(format_plan(plan))
        mancanti = [p["id"] for p in plan if p["stato"] == "misure_mancanti"]
        if mancanti:
            print(f"\nMisure da leggere da Figma prima di correggere: {', '.join(mancanti)}")
        if args.plan_out:
            with open(args.plan_out, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            print(f"\nPiano salvato in: {args.plan_out}")
        sys.exit(0)

    if args.excel and args.apply:
        saved = apply_corrections_and_log(
            args.excel,
            _load_json(args.log_json) or None,
            args.out,
            post_measures=_load_json(args.misure_post),
            before_measures=_load_json(args.misure_prima),
        )
        print(f"Correzioni salvate in: {saved}")
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()

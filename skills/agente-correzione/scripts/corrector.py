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
- Legge il foglio 'Voci' (decisioni del progettista, colonne R-W) e il foglio 'Nodi' (un nodo per riga):
  una voce è un errore comune e può avere più nodi (componente, istanze, nodi singoli)
- Regola "da correggere" (common/lib/nodi_utils.py): Decisione Accolta/Modificata E Chi applica Agente/Entrambi
- Compila il foglio 'Log Correzioni' (una riga per ID errore) e popola la Data della decisione nel foglio 'Voci'
Richiede openpyxl (nessun fallback).
"""

import sys
import os
import json
import argparse
import colorsys  # Libreria nativa Python (Standard Library) per conversioni RGB <-> HLS
from datetime import datetime
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
    from skills.common.lib.nodi_utils import (
        TIPO_COMPONENTE,
        TIPO_ISTANZA,
        da_correggere,
        normalize_nodi,
        post_for_node,
    )
except ImportError:
    from common.lib.color_utils import (  # type: ignore
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
    from common.lib.nodi_utils import (  # type: ignore
        TIPO_COMPONENTE,
        TIPO_ISTANZA,
        da_correggere,
        normalize_nodi,
        post_for_node,
    )

MEASURABLE_REFS = ("1.4.3", "1.4.6", "1.4.11", "2.5.5", "2.5.8")

# Colonne del foglio 'Voci' (layout a 23 colonne generato da checker.py)
COL_ID, COL_PAGINA, COL_ELEMENTO, COL_NODI, COL_AMBITO, COL_RIF, COL_DESC = 1, 2, 3, 4, 5, 6, 7
COL_GRAVITA, COL_CONFLITTO, COL_CORREZIONE, COL_DOVE, COL_SUGG = 8, 12, 14, 15, 16
COL_DECISIONE, COL_MOTIVO_DEC, COL_CHI_APPLICA, COL_DATA_DEC = 18, 19, 22, 23

# Cosa è successo a un nodo durante la correzione (campo "azione" nel file --misure-post)
AZIONI_NODO = {
    "applicato": "corretto",
    "ereditato": "ereditato dal componente (nessuna scrittura)",
    "override": "istanza con override corretta direttamente",
    "libreria": "istanza corretta come override (componente in libreria esterna)",
    "non_trovato": "non trovato o non modificabile",
}
_RANK_ESITO = {"Risolto": 0, "Annotato": 1, "Da verificare": 2, "Non risolto": 3}


def _require_openpyxl() -> None:
    if not HAS_OPENPYXL:
        raise SystemExit(
            "[corrector] ERRORE: openpyxl non è installato. Usa l'ambiente locale del progetto "
            "(<ROOT>/.venv/bin/python) oppure installa le dipendenze: pip install -r requirements.txt"
        )


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
    padding per i target). La voce raggruppa nodi con le STESSE misure, quindi i valori sono uno solo per
    voce e valgono per tutti i suoi nodi. Le misure "prima" vengono da `measures_before` (--misure-prima,
    lette da Figma) oppure dalla colonna Descrizione del report (scritta da checker.py). Se mancano, la voce
    risulta `misure_mancanti`: vanno lette da Figma con get_design_context e passate a --misure-prima.
    I nodi sono già in ordine di applicazione: componente -> istanze -> nodi singoli.
    """
    plan = []
    for item in items:
        vid, ref = item["id"], item.get("riferimento", "")
        nodi = item.get("nodi", [])
        entry: Dict[str, Any] = {
            "id": vid, "riferimento": ref, "elemento": item.get("elemento", ""),
            "nodi": nodi,
        }
        if any(n["tipo"] == TIPO_COMPONENTE for n in nodi):
            # le istanze del componente devono ereditare la correzione: vanno rilette dopo la modifica
            entry["istanze_da_rileggere"] = [n["id"] for n in nodi if n["tipo"] == TIPO_ISTANZA]
        if not _is_measurable(ref):
            entry.update(
                kind="annotazione_o_altro", stato="non_misurabile",
                nota="Nessun valore da calcolare. Inserire l'annotazione su OGNI nodo dell'elenco con il testo guida "
                     "della colonna P, senza compilare i segnaposto tra parentesi quadre.",
                correzione_proposta=item.get("correzione_proposta", ""),
                annotazione=item.get("suggerimento_annotazione", ""),
            )
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
    """Rende il piano leggibile in chat (un blocco per voce, con i nodi in ordine di applicazione)."""
    lines = []
    for p in plan:
        nodi = ", ".join(f"{n['id']} ({n['tipo']})" for n in p["nodi"])
        head = f"{p['id']} [{p['riferimento']}] - {p['elemento']}\n    Nodi (ordine di applicazione): {nodi}"
        if p.get("istanze_da_rileggere"):
            head += f"\n    Dopo la modifica del componente rileggere le istanze: {', '.join(p['istanze_da_rileggere'])}"
        if p["stato"] == "da_correggere" and p["kind"] == "contrasto":
            lines.append(f"{head}\n    {p['testo']}\n    -> nuovo colore {p['suggerito_fg']} ({p['suggerito_ratio']}:1) "
                         f"HLS {p['hls_prima']} -> {p['hls_dopo']} | Figma rgb {p['figma_rgb_suggerito']}")
        elif p["stato"] == "da_correggere" and p["kind"] == "target":
            lines.append(f"{head}\n    {p['testo']}\n    -> +{p['padding_orizzontale_per_lato']:g}px H / +{p['padding_verticale_per_lato']:g}px V per lato "
                         f"=> {p['dimensione_finale'][0]:g}x{p['dimensione_finale'][1]:g} px")
        elif p["stato"] == "non_misurabile":
            lines.append(f"{head}\n    {p['stato']}: {p.get('nota', '')}\n    Annotazione (testo guida, non compilare): {p.get('annotazione') or '-'}")
        else:
            lines.append(f"{head}\n    {p['stato']}: {p.get('nota') or p.get('testo', '')}")
    return "\n".join(lines)


# ==============================================================================
# ESITO PER NODO E PER VOCE
# ==============================================================================

_post_for_node = post_for_node  # definita in common/lib/nodi_utils.py (condivisa con checker.py --verifica)


def _node_outcome(
    item: Dict[str, Any],
    node: Dict[str, str],
    post_node: Dict[str, Any],
    before: Dict[str, Any],
    ha_annotazione: bool,
) -> Tuple[str, str, Optional[str], Optional[Dict[str, Any]]]:
    """Restituisce (azione nodo, esito nodo, riga di verifica o None, misura post o None)."""
    ref = item.get("riferimento", "")
    azione = post_node.get("azione") or "applicato"
    if azione not in AZIONI_NODO:
        print(f"[corrector] AVVISO {item['id']} nodo {node['id']}: azione '{azione}' sconosciuta "
              f"(ammesse: {', '.join(AZIONI_NODO)}); usata 'applicato'.", file=sys.stderr)
        azione = "applicato"
    nota = f" [{post_node['nota']}]" if post_node.get("nota") else ""
    label = f"{node['id']} ({node['tipo']})"

    if azione == "non_trovato":
        return azione, "Non risolto", f"{label}: nodo non trovato o non modificabile{nota}.", None

    if _is_measurable(ref):
        misure = {k: v for k, v in post_node.items() if k in ("fg", "bg", "w", "h", "min")}
        res = None
        if misure:
            merged = dict(before)  # eredita testo_grande / componente_ui dalla misura "prima"
            merged.update(misure)
            res = measure(ref, merged)
        if res:
            esito = "Risolto" if res["compliant"] else "Non risolto"
            testo = res["testo"].replace("Misurato:", "Misurato dopo l'intervento:", 1)
            return azione, esito, f"{label}: {testo}{nota}", res
        return azione, "Da verificare", f"{label}: non misurato (nessuna misura post-intervento fornita){nota}.", None

    # criteri non misurabili da script (annotazioni, Auto Layout/reflow, semantica...)
    return azione, ("Annotato" if ha_annotazione else "Da verificare"), (f"{label}: {nota.strip(' []')}" if nota else None), None


def _riepilogo_azioni(nodi: List[Dict[str, str]], azioni: Dict[str, str], annotando: bool = False) -> str:
    """Riepilogo deterministico, es. 'componente corretto x1; istanza ereditata dal componente x3'.
    Con `annotando` (criteri non misurabili con annotazione) 'corretto/a' diventa 'annotato/a'."""
    etichette = {
        (TIPO_COMPONENTE, "applicato"): "componente corretto",
        (TIPO_ISTANZA, "applicato"): "istanza corretta",
        (TIPO_ISTANZA, "ereditato"): "istanza ereditata dal componente (nessuna scrittura)",
        (TIPO_ISTANZA, "override"): "istanza con override corretta direttamente",
        (TIPO_ISTANZA, "libreria"): "istanza corretta come override (componente in libreria esterna)",
    }
    conteggi: Dict[str, int] = {}
    for n in nodi:
        az = azioni.get(n["id"], "applicato")
        if az == "non_trovato":
            lab = "nodo non trovato o non modificabile"
        else:
            lab = etichette.get((n["tipo"], az)) or ("nodo singolo corretto" if n["tipo"] not in (TIPO_COMPONENTE, TIPO_ISTANZA)
                                                     else f"{n['tipo'].lower()} {AZIONI_NODO.get(az, az)}")
        if annotando:
            lab = lab.replace("corretto", "annotato").replace("corretta", "annotata")
        conteggi[lab] = conteggi.get(lab, 0) + 1
    return "; ".join(f"{lab} x{n}" for lab, n in conteggi.items())


def _build_resolution_details(
    item: Dict[str, Any],
    post_voce: Optional[Dict[str, Any]] = None,
    before_measure: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, str, str]:
    """
    Restituisce (azione, annotazione, esito, verifica) per UNA voce, aggregando i suoi nodi.

    - Annotazione: è SEMPRE il testo guida della colonna P così com'è (con i segnaposto tra parentesi
      quadre non compilati). Non si inventa e non si compila codice.
    - Contrasto e target: la verifica è la misura post-intervento di ciascun nodo, calcolata da
      wcag_checks.measure() sui valori riletti da Figma. Senza misura l'esito del nodo è "Da verificare".
    - Esito della voce = il caso peggiore tra i nodi (Non risolto > Da verificare > Annotato > Risolto).
    - Verifica: una riga per nodo con la sua misura.
    """
    ref = item.get("riferimento", "")
    proposta = item.get("correzione_proposta", "")
    sugg_col_p = item.get("suggerimento_annotazione", "")
    std = lookup_normative_entry(ref)
    nodi = item.get("nodi", [])

    nome_std = std.get("nome", ref)
    techs = ", ".join(std.get("techniques", []))
    tech_str = f" (Tecniche W3C: {techs})" if techs else ""
    annotazione = sugg_col_p if (sugg_col_p and sugg_col_p != "-") else std.get("annotazione_figma", "-")
    ha_annotazione = bool(annotazione) and annotazione not in ["-", "Annotazione già presente in Figma"]

    before = {}
    if _is_measurable(ref):
        before = before_measure or parse_measures_from_text(item.get("descrizione", ""), ref) or {}

    esiti, righe, azioni = [], [], {}
    prima_misura = None
    for n in nodi:
        az, esito_n, riga, res = _node_outcome(item, n, _post_for_node(post_voce, n["id"]), before, ha_annotazione)
        azioni[n["id"]] = az
        esiti.append(esito_n)
        if riga:
            righe.append(riga)
        if res and prima_misura is None:
            prima_misura = res
    esito = max(esiti, key=lambda e: _RANK_ESITO[e]) if esiti else "Da verificare"
    riepilogo = _riepilogo_azioni(nodi, azioni, annotando=(not _is_measurable(ref) and ha_annotazione))

    if _is_measurable(ref):
        if prima_misura and prima_misura["kind"] == "contrasto":
            prima = before.get("fg")
            azione = proposta or "Colore aggiornato su Figma."
            if prima and prima.upper() != prima_misura["fg"]:
                azione = f"Colore aggiornato da {prima.upper()} a {prima_misura['fg']} (tonalità costante, modulazione Lightness HLS)."
        elif prima_misura:
            azione = proposta or "Dimensioni del target aggiornate su Figma."
            if before.get("w") is not None:
                azione = f"Target portato da {before['w']:g}x{before['h']:g} a {prima_misura['w']:g}x{prima_misura['h']:g} px."
        else:
            azione = proposta or f"Intervento su {item.get('elemento', 'componente')} secondo {ref}."
        righe.append(f"{ref} - {nome_std}{tech_str}.")
        return f"{azione} | Nodi: {riepilogo}", annotazione, esito, "\n".join(righe)

    azione = proposta or f"Applicato intervento correttivo su {item.get('elemento', 'componente')} secondo {ref} ({nome_std})."
    if ha_annotazione:
        verifica = (f"Non misurabile da script: annotazione (testo guida, non compilato) inserita su {len(nodi)} {'nodo' if len(nodi) == 1 else 'nodi'} secondo "
                    f"{ref} - {nome_std}{tech_str}. Controllo a cura del progettista.")
    else:
        verifica = f"Non misurabile da script ({ref}): controllo visivo (screenshot) o revisione del progettista."
    return f"{azione} | Nodi: {riepilogo}", annotazione, esito, "\n".join([verifica] + righe)


# ==============================================================================
# LETTURA DECISIONI PROGETTISTA (fogli Voci e Nodi)
# ==============================================================================

def _read_nodi_sheet(wb) -> Dict[str, List[Dict[str, str]]]:
    """Legge il foglio 'Nodi' (una riga per coppia nodo-errore) raggruppando i nodi per ID errore."""
    if "Nodi" not in wb.sheetnames:
        raise ValueError("Foglio 'Nodi' non trovato nel report Excel. Rigenera il report con /audit (versione attuale).")
    ws = wb["Nodi"]
    per_voce: Dict[str, List[Dict[str, str]]] = {}
    for r in range(2, ws.max_row + 1):
        nid = str(ws.cell(r, 1).value or "").strip()
        vid = str(ws.cell(r, 5).value or "").strip()
        if not nid or not vid:
            continue
        per_voce.setdefault(vid, []).append({
            "id": nid,
            "pagina": str(ws.cell(r, 2).value or "").strip(),
            "tipo": str(ws.cell(r, 3).value or "").strip(),
            "elemento": str(ws.cell(r, 4).value or "").strip(),
        })
    # ordine fisso componente -> istanze -> nodi singoli, doppioni eliminati
    return {vid: normalize_nodi(nodi) for vid, nodi in per_voce.items()}


def extract_approved_corrections(excel_path: str) -> List[Dict[str, Any]]:
    """
    Legge il report Excel ed estrae le voci da correggere: Decisione (col. R) Accolta/Modificata E Chi applica
    la correzione (col. V) Agente/Entrambi (regola unica `da_correggere`, uguale alla formula del foglio Nodi).
    Una colonna V vuota NON è approvata. Ogni voce porta TUTTI i suoi nodi, già in ordine di applicazione.
    I nodi si leggono dal foglio 'Nodi' (obbligatorio, nessuna riserva sulla colonna D di 'Voci').
    """
    _require_openpyxl()
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    if "Voci" not in wb.sheetnames:
        raise ValueError("Foglio 'Voci' non trovato nel report Excel.")
    ws = wb["Voci"]
    if "suggerimento" not in str(ws.cell(1, COL_SUGG).value or "").lower():
        raise ValueError(
            "Layout del foglio 'Voci' non riconosciuto (atteso: 23 colonne, colonna P = Suggerimento). "
            "Rigenera il report con /audit."
        )

    nodi_per_voce = _read_nodi_sheet(wb)
    approved = []
    for r in range(2, ws.max_row + 1):
        item_id = ws.cell(r, COL_ID).value
        if not item_id:
            continue
        if not da_correggere(ws.cell(r, COL_DECISIONE).value, ws.cell(r, COL_CHI_APPLICA).value):
            continue
        vid = str(item_id).strip()
        nodi = nodi_per_voce.get(vid)
        if not nodi:
            print(f"[corrector] AVVISO {vid}: da correggere ma senza righe nel foglio Nodi: saltata.", file=sys.stderr)
            continue
        approved.append({
            "id": vid,
            "row": r,
            "pagina": str(ws.cell(r, COL_PAGINA).value or "").strip(),
            "elemento": str(ws.cell(r, COL_ELEMENTO).value or "").strip(),
            "nodi": nodi,
            "ambito": str(ws.cell(r, COL_AMBITO).value or "").strip(),
            "riferimento": str(ws.cell(r, COL_RIF).value or "").strip(),
            "descrizione": str(ws.cell(r, COL_DESC).value or "").strip(),
            "gravita": str(ws.cell(r, COL_GRAVITA).value or "").strip(),
            "conflitto_brand": str(ws.cell(r, COL_CONFLITTO).value or "No").strip(),
            "correzione_proposta": str(ws.cell(r, COL_CORREZIONE).value or "").strip(),
            "dove_si_corregge": str(ws.cell(r, COL_DOVE).value or "").strip(),
            "suggerimento_annotazione": str(ws.cell(r, COL_SUGG).value or "-").strip(),
            "decisione": str(ws.cell(r, COL_DECISIONE).value or "").strip(),
            "motivo_decisione": str(ws.cell(r, COL_MOTIVO_DEC).value or "").strip(),
            "col_data_dec": COL_DATA_DEC,
        })
    return approved


# ==============================================================================
# LOG CORREZIONI (una riga per ID errore)
# ==============================================================================

def apply_corrections_and_log(
    excel_path: str,
    log_overrides: Optional[Dict[str, Dict[str, str]]] = None,
    output_path: Optional[str] = None,
    post_measures: Optional[Dict[str, Dict[str, Any]]] = None,
    before_measures: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """
    Legge le voci approvate da Excel e compila la scheda 'Log Correzioni' (UNA RIGA PER ID ERRORE, così il
    progettista confronta la correzione proposta con quella applicata) e la Data della decisione.

    NON modifica Figma e NON decide i valori: la modifica la fa Claude con use_figma (valori da --plan).
    Qui si registra l'esito: per contrasto e target la verifica è la misura calcolata sui valori riletti da
    Figma, un nodo alla volta (`post_measures`); senza misura l'esito è "Da verificare".
    """
    _require_openpyxl()
    approved_items = extract_approved_corrections(excel_path)
    post_measures = post_measures or {}
    before_measures = before_measures or {}

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
        "ID Voce", "ID Nodi Figma", "Ambito", "Riferimento",
        "Elemento", "Azione Eseguita", "Annotazione / Codice Applicato", "Esito", "Verifica Post-Intervento"
    ]
    ws_log.append(headers)

    today_str = datetime.now().strftime("%Y-%m-%d")
    wrap = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    for item in approved_items:
        item_id = item["id"]
        ref = item.get("riferimento", "")
        elem = item.get("elemento", "")
        ovr = (log_overrides or {}).get(item_id, {})

        def_azione, annotazione, def_esito, def_verifica = _build_resolution_details(
            item, post_measures.get(item_id), before_measures.get(item_id)
        )
        if "annotazione" in ovr:
            print(f"[corrector] AVVISO {item_id}: override di 'annotazione' ignorato: si riporta il suggerimento della "
                  "colonna P così com'è (testo guida, mai codice compilato).", file=sys.stderr)
        azione = ovr.get("azione", def_azione)
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
            "\n".join(n["id"] for n in item["nodi"]),
            item["ambito"],
            ref,
            elem,
            azione,
            annotazione,
            esito,
            verifica
        ])
        for c in ws_log[ws_log.max_row]:
            c.alignment = wrap
        col_data = item.get("col_data_dec", COL_DATA_DEC)
        if not ws_voci.cell(item["row"], col_data).value:
            ws_voci.cell(item["row"], col_data, today_str)

    target_path = output_path or excel_path
    wb.save(target_path)
    return target_path


def main():
    parser = argparse.ArgumentParser(
        description="corrector.py — Piano di correzione calcolato (--plan) e Log Correzioni con verifica misurata (--apply)"
    )
    parser.add_argument("--demo", action="store_true", help="Solo test delle formule (colore HLS, padding, regola Da correggere). NON legge l'Excel")
    parser.add_argument("--excel", help="Percorso del report Excel di audit contenente le decisioni")
    parser.add_argument("--plan", action="store_true",
                        help="Dry-run: legge l'Excel, elenca le voci approvate con i loro nodi e calcola i valori da applicare su Figma. Non scrive nulla")
    parser.add_argument("--plan-out", help="Con --plan: salva anche il piano in JSON (valori colore/padding e nodi per voce)")
    parser.add_argument("--misure-prima", help="JSON {ID voce: {fg,bg | w,h}} con le misure lette da Figma PRIMA della modifica")
    parser.add_argument("--apply", action="store_true", help="Scrive il foglio Log Correzioni (verifica = misure post-intervento per nodo)")
    parser.add_argument("--misure-post", help="JSON {ID voce: {fg,bg | w,h}} oppure {ID voce: {ID nodo: {fg,bg | w,h, azione, nota}}} "
                                              "con le misure rilette da Figma DOPO la modifica")
    parser.add_argument("--log-json", help="Percorso file JSON opzionale con override per voce (solo 'azione'; 'esito'/'verifica' solo per criteri non misurabili)")
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
        print("Regola 'Da correggere' (Decisione, Chi applica): "
              f"(Accolta, Agente)={da_correggere('Accolta', 'Agente')} | (Accolta, Progettista)={da_correggere('Accolta', 'Progettista')} | "
              f"(Rifiutata, Entrambi)={da_correggere('Rifiutata', 'Entrambi')} | (Accolta, vuoto)={da_correggere('Accolta', None)}")
        sys.exit(0)

    if args.excel and args.plan:
        items = extract_approved_corrections(args.excel)
        if not items:
            print("Nessuna voce da correggere (serve Decisione Accolta/Modificata E Chi applica = Agente/Entrambi).")
            sys.exit(0)
        plan = build_correction_plan(items, _load_json(args.misure_prima))
        tot_nodi = sum(len(p["nodi"]) for p in plan)
        print(f"Voci da correggere: {len(items)}, nodi totali: {tot_nodi} (dry-run: nessun file modificato)\n")
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

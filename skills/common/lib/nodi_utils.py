"""
nodi_utils.py — Gestione condivisa dei nodi Figma di una voce di audit (audit e correzione).

Una voce (riga del foglio `Voci`) è un errore comune e può riguardare più nodi Figma:
componenti, istanze e nodi singoli. Questo modulo, a 0 token:
- normalizza l'elenco dei nodi di una voce (tipo, duplicati, ordine fisso);
- scrive l'elenco nella colonna D di `Voci` (un ID per riga; `/correzione` legge i nodi dal foglio `Nodi`);
- definisce in un solo punto la regola "Da correggere" (Decisione + Chi applica) sia come
  formula Excel (scritta da checker.py nel foglio `Nodi`) sia come funzione Python
  (usata da corrector.py, che non si fida del valore salvato nella cella).
"""

from typing import Any, Callable, Dict, List, Optional

# ------------------------------------------------------------------------------
# Costanti condivise (definite una sola volta)
# ------------------------------------------------------------------------------
TIPO_COMPONENTE = "Componente"
TIPO_ISTANZA = "Istanza"
TIPO_NODO_SINGOLO = "Nodo singolo"
TIPI_NODO = (TIPO_COMPONENTE, TIPO_ISTANZA, TIPO_NODO_SINGOLO)

# Ordine di applicazione delle correzioni: prima il componente, poi le istanze, poi i nodi singoli.
_ORDINE_TIPO = {TIPO_COMPONENTE: 0, TIPO_ISTANZA: 1, TIPO_NODO_SINGOLO: 2}

_SINONIMI_TIPO = {
    "componente": TIPO_COMPONENTE, "component": TIPO_COMPONENTE, "main component": TIPO_COMPONENTE,
    "component_set": TIPO_COMPONENTE, "master": TIPO_COMPONENTE, "symbol": TIPO_COMPONENTE,
    "istanza": TIPO_ISTANZA, "instance": TIPO_ISTANZA,
    "nodo singolo": TIPO_NODO_SINGOLO, "nodo": TIPO_NODO_SINGOLO, "singolo": TIPO_NODO_SINGOLO,
    "frame": TIPO_NODO_SINGOLO, "frame di pagina": TIPO_NODO_SINGOLO, "layer": TIPO_NODO_SINGOLO,
}

# Valori del foglio `Voci` che rendono un nodo "Da correggere = Sì" (devono valere ENTRAMBE le condizioni)
DECISIONI_APPROVATE = ("Accolta", "Modificata")          # colonna R "Decisione"
CHI_APPLICA_AGENTE = ("Agente", "Entrambi")              # colonna V "Chi applica la correzione"
MAX_RIGHE_VOCI = 2000                                    # righe del foglio Voci lette dalla formula
COL_VOCI_ID = "A"
COL_VOCI_DECISIONE = "R"
COL_VOCI_CHI_APPLICA = "V"


# ------------------------------------------------------------------------------
# Nodi di una voce
# ------------------------------------------------------------------------------
def infer_tipo_nodo(node_id: str) -> str:
    """Tipo dedotto dal solo ID quando il payload non lo dichiara.
    `I1:2431;1:14076` è un nodo dentro un'istanza; gli altri ID sono nodi singoli (il componente va dichiarato)."""
    nid = str(node_id).strip()
    return TIPO_ISTANZA if nid.startswith("I") and ";" in nid else TIPO_NODO_SINGOLO


def normalize_tipo_nodo(tipo: Any, node_id: str = "") -> Optional[str]:
    """Porta il tipo ai valori ammessi. Tipo mancante -> dedotto dall'ID. Tipo sconosciuto -> None."""
    t = str(tipo or "").strip().lower()
    if not t:
        return infer_tipo_nodo(node_id)
    return _SINONIMI_TIPO.get(t)


def normalize_nodi(
    nodi: List[Any],
    default_pagina: str = "",
    default_elemento: str = "",
    warn: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, str]]:
    """
    Normalizza l'elenco `nodi` di una voce: ogni elemento è un dict {id, pagina, tipo, elemento} oppure
    una semplice stringa (solo ID). Elimina i duplicati (stesso ID) e ordina in modo fisso:
    componente -> istanze -> nodi singoli (a parità di tipo resta l'ordine del payload).
    """
    warn = warn or (lambda _msg: None)
    out: List[Dict[str, str]] = []
    visti = set()
    for raw in nodi or []:
        n = {"id": raw} if isinstance(raw, str) else dict(raw or {})
        nid = str(n.get("id") or n.get("nodo_id") or "").strip()
        if not nid:
            warn("nodo senza 'id' ignorato")
            continue
        if nid in visti:
            warn(f"nodo {nid} duplicato nella stessa voce: tenuto una sola volta")
            continue
        visti.add(nid)
        tipo = normalize_tipo_nodo(n.get("tipo"), nid)
        if tipo is None:
            warn(f"nodo {nid}: tipo '{n.get('tipo')}' non valido (ammessi: {', '.join(TIPI_NODO)}); usato '{infer_tipo_nodo(nid)}'")
            tipo = infer_tipo_nodo(nid)
        out.append({
            "id": nid,
            "pagina": str(n.get("pagina") or default_pagina or "").strip(),
            "tipo": tipo,
            "elemento": str(n.get("elemento") or default_elemento or "").strip(),
        })
    out.sort(key=lambda x: _ORDINE_TIPO[x["tipo"]])  # sort stabile
    return out


def nodi_to_cell(nodi: List[Dict[str, str]]) -> str:
    """Contenuto della colonna D di `Voci`: un ID nodo per riga (il `;` non può fare da separatore: è dentro gli ID `I1:2;1:3`)."""
    return "\n".join(n["id"] for n in nodi)


# ------------------------------------------------------------------------------
# Regola "Da correggere"
# ------------------------------------------------------------------------------
def da_correggere(decisione: Any, chi_applica: Any) -> bool:
    """
    Regola unica: Sì SOLO se Decisione è Accolta/Modificata E Chi applica è Agente/Entrambi.
    Rifiutata, vuota, 'Progettista' o cella V vuota -> No. Confronto senza distinzione maiuscole/minuscole.
    """
    dec = str(decisione or "").strip().lower()
    chi = str(chi_applica or "").strip().lower()
    return dec in {d.lower() for d in DECISIONI_APPROVATE} and chi in {c.lower() for c in CHI_APPLICA_AGENTE}


def formula_da_correggere(riga: int, col_id_errore: str = "E") -> str:
    """
    Formula Excel per la colonna 'Da correggere' del foglio `Nodi` (stessa regola di `da_correggere`).
    Cerca l'ID errore della riga nel foglio `Voci` e legge Decisione (R) e Chi applica (V).
    Qualsiasi errore di ricerca (ID non trovato) -> "No".
    """
    def rng(col: str) -> str:  # intervallo delimitato (non colonna intera): compatibile con Excel, Numbers e LibreOffice
        return f"Voci!${col}$1:${col}${MAX_RIGHE_VOCI}"

    match = f"MATCH(${col_id_errore}{riga},{rng(COL_VOCI_ID)},0)"
    dec = f"INDEX({rng(COL_VOCI_DECISIONE)},{match})"
    chi = f"INDEX({rng(COL_VOCI_CHI_APPLICA)},{match})"
    cond_dec = ",".join(f'{dec}="{d}"' for d in DECISIONI_APPROVATE)
    cond_chi = ",".join(f'{chi}="{c}"' for c in CHI_APPLICA_AGENTE)
    return f'=IFERROR(IF(AND(OR({cond_dec}),OR({cond_chi})),"Sì","No"),"No")'

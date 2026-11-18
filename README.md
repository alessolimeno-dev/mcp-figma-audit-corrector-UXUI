# mcp-figma-audit-corrector-UXUI

Skill per **Claude Code** che analizzano (audit) e correggono l'usabilità e l'accessibilità di prototipi UI/UX in Figma.

---

## Panoramica

Claude, collegato a Figma tramite il connettore MCP ufficiale, esegue due skill in sequenza rispettando il principio **Human-in-the-Loop**:
1. **`agente-audit`** (`/audit`): analizza usabilità (10 Euristiche di Nielsen) e accessibilità (W3C WCAG 2.2) e produce un report Excel strutturato. Sola lettura (`READ-ONLY`). Con anche il report Excel (`/audit [link] [file-excel]`) fa la **verifica post-correzione**: rilegge i nodi corretti, segnala regressioni ed errori nuovi (`N-xx`) e aggiunge allo stesso report un foglio nuovo `Verifica N` (uno per ogni verifica) con gli esiti e il blocco «A correzione effettuata».
2. **Revisione umana**: il progettista compila il Registro delle Decisioni nel foglio Excel (`Accolta`, `Modificata`, ecc.).
3. **`agente-correzione`** (`/correzione`): interviene su **tutti i nodi** degli errori approvati (componenti, istanze e nodi singoli, in ogni pagina) e compila il foglio `Log Correzioni` (`WRITE-BOUNDED`).

---

## Nodi, errori comuni e "Da correggere"

Le regole valgono per **qualsiasi file Figma**: nessuna skill, script o modulo contiene ID, nomi o regole di un progetto specifico.

- **Una voce = un errore comune.** Il foglio `Voci` ha una riga per errore; in colonna D elenca tutti i nodi che lo condividono (uno per riga della cella). Il raggruppamento lo fa `checker.py` a 0 token: contrasto e dimensioni si uniscono solo con **misure identiche**; gli altri criteri solo con la stessa descrizione. Nel dubbio la voce si divide.
- **Foglio `Nodi`:** una riga per ogni coppia nodo-errore, solo per i nodi con un errore. Colonne: ID nodo Figma, Pagina, Tipo (`Componente`, `Istanza`, `Nodo singolo`), Elemento, ID errore riferimento, Da correggere.
- **Da correggere** è una formula: vale `Sì` solo se, nella voce collegata, la Decisione (col. R) è `Accolta` o `Modificata` **e** "Chi applica la correzione" (col. V) è `Agente` o `Entrambi`; altrimenti `No`. Non si compila a mano. `corrector.py` ricalcola la stessa regola da R e V.
- **Ordine di correzione:** prima il componente, poi le istanze (si rileggono: se hanno ereditato la correzione non si riscrivono, se hanno un override si correggono), poi i nodi singoli. Una chiamata `use_figma` per voce.
- **Annotazioni:** il suggerimento della colonna P è un testo guida con segnaposto tra parentesi quadre; la correzione lo riporta così com'è su ogni nodo, senza compilare il codice. L'annotazione si scrive con `labelMarkdown`, mai con `label` (Figma convertirebbe `<`, `>` e `"` in entità HTML).

> Si segnala che l'inserimento automatizzato di tali annotazioni direttamente in Figma richiede un piano in abbonamento e non è supportato dal piano gratuito.

---

## Requisito obbligatorio: connettore Figma su Claude

Le skill leggono e modificano Figma **solo** tramite il connettore Figma ufficiale collegato al tuo account Claude. Il repository non contiene una configurazione MCP propria: senza il connettore attivo le skill non possono funzionare.

Come attivarlo (una volta per account):
1. Apri [claude.ai](https://claude.ai) → **Impostazioni → Connettori** e aggiungi **Figma**.
2. Accedi con il tuo account Figma e autorizza l'accesso ai file.
3. Usa Claude Code con lo **stesso account** (app desktop, web o terminale): il connettore compare da solo tra gli strumenti della sessione.

Per verificare che funzioni, chiedi a Claude in una sessione di questo progetto: *"Quali strumenti Figma hai disponibili?"*. Devono comparire almeno `create_session`, `get_metadata`, `get_design_context`, `get_variable_defs`, `get_screenshot` e `use_figma`.

Chi clona il repository deve attivare il connettore sul **proprio** account Claude e avere accesso al file Figma da analizzare.

---

## Strumenti Figma consentiti

Ogni skill usa un elenco chiuso di strumenti. L'hook `skills/common/lib/figma_guard.py` lo fa rispettare: blocca qualunque altro strumento Figma mentre il comando è attivo.

| Strumento | `/audit` | `/correzione` | A cosa serve |
|---|:-:|:-:|---|
| `create_session` | ✅ | ✅ | Apre la sessione di lavoro sul file (obbligatorio, non modifica nulla) |
| `get_metadata` | ✅ | ✅ | Struttura di pagine e frame, ID nodi, dimensioni |
| `get_variable_defs` | ✅ | ✅ | Variabili e stili di colore e testo |
| `get_design_context` | ✅ | ✅ | Dettaglio di un nodo: colori, testi, layout |
| `get_screenshot` | ✅ | ✅ | Immagine del frame per il giudizio visivo |
| `use_figma` | ❌ | ✅ | **Unico strumento che modifica il file**, solo sui nodi approvati |

Fuori da `/audit` e `/correzione` l'hook non blocca nulla.

---

## Struttura del repository

```text
mcp-figma-audit-corrector-UXUI/
├── .claude/
│   ├── commands/
│   │   ├── audit.md               # Comando /audit
│   │   └── correzione.md          # Comando /correzione
│   └── settings.json              # Hook: figma_guard (PreToolUse) e token_log (Stop)
├── skills/
│   ├── README.md                  # Panoramica delle skill
│   ├── common/
│   │   ├── references/
│   │   │   └── wcag.json          # Dataset W3C WCAG 2.2 + 10 Euristiche di Nielsen
│   │   └── lib/
│   │       ├── color_utils.py     # Contrasto, luminanza, modulazione colore HLS
│   │       ├── wcag_checks.py     # check_contrast / check_target_size / measure (usate da checker e corrector)
│   │       ├── normative.py       # Caricamento normativo da wcag.json
│   │       ├── excel_utils.py     # Rilevamento di OpenPyXL (obbligatorio)
│   │       ├── nodi_utils.py      # Nodi di una voce, ordine fisso e regola "Da correggere" (formula + Python)
│   │       ├── figma_guard.py     # Hook: limita gli strumenti Figma per skill
│   │       └── token_log.py       # Hook: registra i token reali in logs/
│   ├── agente-audit/
│   │   ├── SKILL.md               # Regole dell'Agente di Audit
│   │   └── scripts/checker.py     # Calcoli deterministici e generazione del report
│   └── agente-correzione/
│       ├── SKILL.md               # Regole dell'Agente di Correzione
│       └── scripts/corrector.py   # Estrazione decisioni approvate e Log Correzioni
├── Audit_modello.xlsx             # Template del report Excel
├── CLAUDE.md                      # Linee guida operative per Claude Code
├── requirements.txt               # Dipendenze Python
├── LICENSE
└── README.md
```

La cartella `logs/` (log dei token) e la cartella `.venv/` sono locali e non vengono versionate.

---

## Moduli e ruoli

| Componente | Tipo | Ruolo |
|---|---|---|
| `skills/common/references/wcag.json` | Dati | Dataset normativo (86 criteri WCAG 2.2 + 10 Euristiche di Nielsen) |
| `skills/common/lib/` | Libreria | Calcoli colore, caricamento normativo, gestione Excel, hook |
| `skills/agente-audit/SKILL.md` | Skill | Regole di analisi UI/UX (`READ-ONLY`) |
| `skills/agente-audit/scripts/checker.py` | Script | Contrasto, target size, raggruppamento degli errori comuni e scrittura del report Excel (fogli `Voci` e `Nodi`); con `--verifica` confronto post-correzione (foglio `Verifica N` nello stesso report, con il blocco «A correzione effettuata»), senza token AI |
| `skills/agente-correzione/SKILL.md` | Skill | Regole di modifica mirata su Figma (`WRITE-BOUNDED`) |
| `skills/agente-correzione/scripts/corrector.py` | Script | Voci da correggere con tutti i loro nodi, calcolo correzioni colore/padding, Log Correzioni (una riga per ID errore) |

---

## Utilizzo

In una sessione di Claude Code aperta in questa cartella (o nella cartella superiore che la contiene):

```text
/audit [link-file-figma]
/audit [link-file-figma] [percorso-report.xlsx]     # verifica post-correzione
/correzione [link-file-figma] [percorso-report-audit.xlsx]
```

Il report viene salvato in una cartella con il nome del file Figma analizzato: `<nome file Figma>/<nome file Figma>-<data>-audit.xlsx`.

---

## Installazione

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Gli script usano sempre l'interprete del progetto (`./.venv/bin/python`). `openpyxl` è **obbligatoria**: senza, `checker.py` e `corrector.py` si fermano con un messaggio chiaro (non esiste più un motore Excel di riserva). `wcag-contrast-ratio` è opzionale (senza, il contrasto si calcola con un metodo nativo equivalente); `colorbrew` non è installabile da PyPI ed è facoltativa.

Test rapido:

```bash
./.venv/bin/python skills/agente-audit/scripts/checker.py --demo          # librerie, suggerimenti e raggruppamento di esempio
./.venv/bin/python skills/agente-correzione/scripts/corrector.py --demo   # solo formule; per il piano reale: --excel <report.xlsx> --plan
```

Gli hook in `.claude/settings.json` si attivano nelle sessioni di Claude Code aperte **dopo** la loro configurazione.

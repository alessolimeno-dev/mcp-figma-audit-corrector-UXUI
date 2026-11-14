# mcp-figma-audit-corrector-UXUI

Skill per **Claude Code** che analizzano (audit) e correggono l'usabilità e l'accessibilità di prototipi UI/UX in Figma.

---

## Panoramica

Claude, collegato a Figma tramite il connettore MCP ufficiale, esegue due skill in sequenza rispettando il principio **Human-in-the-Loop**:
1. **`agente-audit`** (`/audit`): analizza usabilità (10 Euristiche di Nielsen) e accessibilità (W3C WCAG 2.2) e produce un report Excel strutturato. Sola lettura (`READ-ONLY`).
2. **Revisione umana**: il progettista compila il Registro delle Decisioni nel foglio Excel (`Accolta`, `Modificata`, ecc.).
3. **`agente-correzione`** (`/correzione`): interviene sui soli nodi approvati in Figma e compila il foglio `Log Correzioni` (`WRITE-BOUNDED`).

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
│   │       ├── normative.py       # Caricamento normativo da wcag.json
│   │       ├── excel_utils.py     # Gestione OpenPyXL e fallback OpenXML
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
| `skills/agente-audit/scripts/checker.py` | Script | Contrasto, target size e scrittura del report Excel, senza token AI |
| `skills/agente-correzione/SKILL.md` | Skill | Regole di modifica mirata su Figma (`WRITE-BOUNDED`) |
| `skills/agente-correzione/scripts/corrector.py` | Script | Righe approvate, calcolo correzioni colore/padding, Log Correzioni |

---

## Utilizzo

In una sessione di Claude Code aperta in questa cartella (o nella cartella superiore che la contiene):

```text
/audit [link-file-figma]
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

Gli script usano sempre l'interprete del progetto (`./.venv/bin/python`). Senza le dipendenze funzionano comunque con la sola libreria standard di Python, con un motore Excel di riserva.

Test rapido:

```bash
./.venv/bin/python skills/agente-audit/scripts/checker.py --demo
./.venv/bin/python skills/agente-correzione/scripts/corrector.py --demo
```

Gli hook in `.claude/settings.json` si attivano nelle sessioni di Claude Code aperte **dopo** la loro configurazione.

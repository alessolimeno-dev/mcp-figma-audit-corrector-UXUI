# mcp-figma-audit-corrector-UXUI

Skills per Figma per l'analisi (audit) e la correzione di usabilità ed accessibilità su prototipi UI/UX. Compatibile con **Claude Code** e **Antigravity**.

---

## Panoramica

Un agente collegato a Figma tramite connettore MCP esegue due skill in sequenza rispettando il principio **Human-in-the-Loop**:
1. **`agente-audit`**: analizza usabilità (10 Euristiche di Nielsen) e accessibilità (W3C WCAG 2.2) producendo un report Excel strutturato (`READ-ONLY`).
2. **Revisione Umana**: il progettista compila il Registro delle Decisioni nel foglio Excel (`Accolta`, `Modificata`, ecc.).
3. **`agente-correzione`**: interviene chirurgicamente sui soli nodi approvati su Figma e compila il foglio `Log Correzioni` (`WRITE-BOUNDED`).

---

## Architettura del Repository

```text
mcp-figma-audit-corrector-UXUI/
├── .antigravity/                   # Configurazione per Antigravity
│   ├── mcp_config.json            # Template connettore MCP Figma
│   └── rules.md                   # Regole di esecuzione workspace
├── .agents/                        # Configurazione nativa Antigravity
│   ├── rules/
│   │   └── audit-corrector.md     # Regola di instradamento verso skills/
│   └── skills.json                # Registrazione del percorso skills/ condiviso
├── .claude/                        # Configurazione per Claude Code
│   ├── commands/
│   │   ├── audit.md               # Definizione slash command /audit
│   │   └── correttore.md          # Definizione slash command /correttore
│   └── mcp.json                   # Configurazione connettore MCP Figma per Claude
├── skills/
│   ├── README.md                  # Panoramica della base comune delle skill
│   ├── common/                    # Risorse e utility condivise (0 token AI)
│   │   ├── references/
│   │   │   └── wcag.json          # Dataset unico W3C WCAG 2.2 + 10 Euristiche Nielsen
│   │   └── lib/                   # Moduli Python condivisi
│   │       ├── color_utils.py     # Contrasto, luminanza, modulazione colore HLS
│   │       ├── normative.py       # Parser e caricamento normativo da wcag.json
│   │       └── excel_utils.py     # Gestione OpenPyXL e fallback OpenXML
│   ├── agente-audit/
│   │   ├── SKILL.md               # Definizione e regole per l'Agente di Audit
│   │   └── scripts/
│   │       └── checker.py         # Motore deterministico di calcolo e generazione report
│   └── agente-correzione/
│       ├── SKILL.md               # Definizione e regole per l'Agente di Correzione
│       └── scripts/
│           └── corrector.py       # Motore deterministico di estrazione decisioni e log
├── CLAUDE.md                      # Linee guida operative per Claude Code
├── requirements.txt               # Dipendenze Python consigliate
├── LICENSE
└── README.md
```

---

## Moduli e Ruoli

| Componente | Tipo | Ruolo |
|---|---|---|
| `skills/common/references/wcag.json` | Dati | Dataset normativo completo (86 criteri WCAG 2.2 + 10 Euristiche Nielsen). |
| `skills/common/lib/` | Libreria | Calcoli matematici colore, caricamento normativo e gestione Excel riutilizzabili. |
| `skills/agente-audit/SKILL.md` | Skill | Regole di analisi e diagnosi UI/UX (`READ-ONLY`). |
| `skills/agente-audit/scripts/checker.py` | Script | Calcoli deterministici (contrasto, target size) e scrittura Excel a 0 token AI. |
| `skills/agente-correzione/SKILL.md` | Skill | Regole di modifica mirata su Figma e prescrizioni di codice (`WRITE-BOUNDED`). |
| `skills/agente-correzione/scripts/corrector.py` | Script | Estrazione righe approvate, calcolo correzioni colore/padding e compilazione log. |

---

## Modalità di Invocazione

### 1. Con Claude Code
Nella sessione di Claude Code sono disponibili i comandi slash dedicati:
* **Audit:**
  ```text
  /audit [link-progetto-figma]
  ```
* **Correzione:**
  ```text
  /correttore [link-progetto-figma] [percorso-report-audit.xlsx]
  ```

### 2. Con Antigravity
Grazie al puntatore `.agents/skills.json` e alla regola in `.agents/rules/audit-corrector.md`, Antigravity rileva direttamente la cartella comune `skills/`:
* **Attivazione Audit:** chiedi all'agente di eseguire l'audit di usabilità e accessibilità fornendo il link Figma. L'agente attiverà `agente-audit` ed eseguirà `checker.py`.
* **Attivazione Correzione:** fornisci all'agente il file Excel con le decisioni approvate. L'agente attiverà `agente-correzione` ed eseguirà `corrector.py`.

---

## Requisiti e Installazione

Gli script Python funzionano con le librerie standard native di Python (`colorsys`, `math`, `zipfile`, `xml.etree.ElementTree`). Per la massima precisione e velocità di calcolo, è consigliato installare le dipendenze:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Test rapido di funzionamento:
```bash
./.venv/bin/python skills/agente-audit/scripts/checker.py --demo
./.venv/bin/python skills/agente-correzione/scripts/corrector.py --demo
```

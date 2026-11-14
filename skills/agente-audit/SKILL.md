---
name: agente-audit
description: Esegue l'audit euristico (10 Euristiche di Nielsen) e normativo (W3C WCAG 2.2) in sola lettura (READ-ONLY) su prototipi Figma ed esporta il report Excel strutturato.
---

# Skill: Agente di Audit UI/UX (Fase 1)

Definizione canonica condivisa per **Claude Code** e **Antigravity**.

---

## 1. Ambiente di Esecuzione (VENV Locale)

- **Cartella del progetto (`<ROOT>`):** la cartella che contiene `skills/`, `.venv/` e `Audit_modello.xlsx`.
  - Se la sessione è aperta dentro il progetto: `<ROOT>` = `.`
  - Se la sessione è aperta nella cartella superiore (es. `Analisi-skills/`): `<ROOT>` = `mcp-figma-audit-corrector-UXUI`
- **Interprete Python Obbligatorio:** tutte le chiamate agli script devono usare il python locale del progetto:
  - macOS/Linux: `<ROOT>/.venv/bin/python`
  - Windows: `<ROOT>\.venv\Scripts\python.exe`
- Non utilizzare l'interprete Python globale di sistema.

---

## 2. Integrazione con i Moduli Comuni (`skills/common/`)

L'agente delega i calcoli e le definizioni ai moduli condivisi della cartella `skills/common/`:
- **`skills/common/references/wcag.json`:** dizionario unico con 86 criteri W3C WCAG 2.2 e 10 Euristiche di Nielsen.
- **`skills/common/lib/normative.py`:** carica a 0 token il dizionario normativo ed estrae metadati e tecniche ufficiali (es. ARIA14, H37, H42).
- **`skills/common/lib/color_utils.py`:** esegue il calcolo deterministico del rapporto di contrasto (`contrast_ratio`) e la luminanza relativa.
- **`skills/common/lib/excel_utils.py`:** gestisce la clonazione del template Excel e la scrittura dei fogli di calcolo.

---

## 3. Definizione INPUT

1. **Link Prototipo Figma (`link_figma`):**
   - URL Figma fornito dall'utente (es. `https://www.figma.com/design/<file-key>/<titolo>?node-id=...`).
   - L'agente estrae via connettore MCP (`get_figma_data` o `get_file`) i nodi dei frame Desktop e Mobile.
2. **Template Excel (`Audit_modello.xlsx`):**
   - Modello base contenente i fogli `Sessione`, `Voci`, `Corretto`, `Riepilogo`.
3. **Payload Dati (formato JSON per lo script):**
   - L'agente sintetizza i risultati dell'ispezione in una struttura JSON:
     ```json
     {
       "session": {
         "caso": "Nome Progetto / Flusso",
         "link_figma": "https://www.figma.com/design/...",
         "file_figma": "Nome File",
         "versione": "v0 (pre-audit)",
         "pagine": "Desktop e Mobile"
       },
       "voci": [
         {
           "id": "V-01",
           "pagina": "Desktop / Home",
           "elemento": "Pulsante CTA Carrello",
           "nodo_id": "12:34",
           "riferimento": "WCAG 1.4.3 (AA)",
           "descrizione": "Contrasto testo insufficiente (#888888 su #FFFFFF, ratio 3.5:1)",
           "gravita": "Moderata",
           "correzione": "Aumentare contrasto a 4.5:1"
         }
       ],
       "corretto": [
         {
           "pagina": "Desktop / Header",
           "elemento": "Logo brand",
           "riferimento": "WCAG 1.1.1 (A)",
           "descrizione": "Logo vettoriale con testo alternativo presente"
         }
       ]
     }
     ```

---

## 4. Elaborazione e Logica Operativa (`READ-ONLY`)

- **Modalità Operativa:** `READ-ONLY`. Divieto categorico di modificare il file Figma.
- **Calcoli Deterministici a 0 Token:**
  - Contrasto cromatico testo (WCAG 1.4.3: $\ge 4.5:1$ per testo normale, $\ge 3.0:1$ per testo grande $\ge 18$pt o $\ge 14$pt bold).
  - Contrasto componenti grafici e stati interattivi (WCAG 1.4.11: $\ge 3.0:1$).
  - Dimensioni target touch/click (WCAG 2.5.8: $\ge 24\times 24$ px, WCAG 2.5.5: $\ge 44\times 44$ px).
- **Auto-popolamento Tecniche W3C (Colonna P):**
  - Lo script associa in automatico le tecniche W3C (es. `ARIA14` per icone interattive, `H37` per immagini) per prescrivere annotazioni per gli sviluppatori.

---

## 5. Comando di Esecuzione dello Script

### Cartella di output
Il report viene **sempre** salvato in una cartella con il nome del file Figma analizzato (`session.file_figma`):
`<cartella corrente>/<nome file Figma>/<nome file Figma>-<data>-audit.xlsx`.
Lo script crea la cartella da solo; `--out-root` cambia la cartella base. Salva anche il `payload.json` dentro la stessa cartella.

```bash
# Esecuzione con file JSON:
<ROOT>/.venv/bin/python <ROOT>/skills/agente-audit/scripts/checker.py \
  --template <ROOT>/Audit_modello.xlsx \
  --input-json "<nome file Figma>/payload.json"

# In alternativa via standard input:
cat payload.json | <ROOT>/.venv/bin/python <ROOT>/skills/agente-audit/scripts/checker.py \
  --template <ROOT>/Audit_modello.xlsx \
  --stdin

# Verifica preliminare dataset e formule:
<ROOT>/.venv/bin/python <ROOT>/skills/agente-audit/scripts/checker.py --demo
```

---

## 6. Definizione OUTPUT

- **File Excel di Audit Generato (`<nome file Figma>/<nome file Figma>-<data>-audit.xlsx`):**
  1. **Foglio `Sessione`:** metadati completi dell'audit.
  2. **Foglio `Voci` (23 Colonne):**
     - *Colonne A-Q compilate dall'agente:* `ID`, `Pagina`, `Elemento`, `ID Nodo Figma` (colonna D), `Ambito`, `Riferimento`, `Descrizione`, `Gravità`, `Stato`, `Affidabilità`, `Motivo`, `Conflitto`, `Motivo conflitto`, `Correzione proposta`, `Dove si corregge`, `Suggerimento (Annotazioni in Figma)` (colonna P), `Fonte`.
     - *Colonne R-W vuote (riservate al Progettista):* `Decisione`, `Motivo`, `Tipo motivo`, `Gravità confermata`, `Chi applica la correzione`, `Data decisione`.
  3. **Foglio `Corretto`:** elementi esaminati e conformi.
  4. **Foglio `Riepilogo`:** matrice d'impatto incrociata (Gravità $\times$ Ambito).
- **Passaggio di Consegna:** l'agente comunica all'utente in chat:
  1. il percorso del file generato;
  2. il promemoria: *"Prima della Fase 2 (correzione), salva una copia locale del file Figma: File → Save local copy… (.fig)"*.
  Poi attende che il progettista compili le decisioni (Human-in-the-Loop).

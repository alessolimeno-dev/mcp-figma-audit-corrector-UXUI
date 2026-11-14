---
name: agente-correzione
description: Applica sul prototipo Figma le correzioni approvate dal progettista nel report Excel (WRITE-BOUNDED) con il principio di minima invasività e compila il foglio Log Correzioni.
---

# Skill: Agente di Correzione UI/UX (Fase 2)

Definizione canonica per **Claude Code**. Figma si raggiunge solo tramite il connettore Figma attivo sull'account Claude.

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

L'agente sfrutta gli stessi moduli matematici e normativi impiegati nella Fase 1:
- **`skills/common/references/wcag.json`:** dizionario normativo condiviso con l'agente di audit.
- **`skills/common/lib/normative.py`:** mappa ciascun ID anomalia alle prescrizioni e tecniche ufficiali per la generazione del log.
- **`skills/common/lib/color_utils.py`:**
  - `adjust_lightness_for_contrast(fg_hex, bg_hex, target_ratio)`: modula deterministicamente la luminosità (Lightness) in coordinate HLS mantenendo invariata la tonalità (Hue).
  - `calculate_padding_expansion(width, height, min_target)`: calcola l'incremento di padding orizzontale e verticale per raggiungere i target minimi (es. 24px o 44px).
- **`skills/common/lib/excel_utils.py`:** legge il foglio `Voci`, compila il foglio `Log Correzioni` e popola la data della decisione nel foglio `Voci`.

---

## 3. Definizione INPUT

1. **Link Prototipo Figma (`link_figma`):**
   - URL del progetto Figma su cui risiedono i nodi da correggere.
2. **File Excel di Audit con Decisioni Compilate (`file_excel`):**
   - Il report generato nella Fase 1 in cui il progettista ha compilato le colonne R-W nel foglio `Voci`.
3. **Criteri di Filtraggio Decisionale (Human-in-the-Loop):**
   - Vengono estratte ed elaborate solo le righe che soddisfano contemporaneamente:
     - Colonna R (`Decisione`): `Accolta` oppure `Modificata`.
     - Colonna V (`Chi applica la correzione`): `Agente` oppure `Entrambi`.
   - Voci `Rifiutata`, `Da valutare` o assegnate esclusivamente al `Progettista` non vengono toccate.

---

## 4. Elaborazione e Logica Operativa (`WRITE-BOUNDED`)

### Promemoria copia locale (non bloccante)
All'inizio l'agente suggerisce in chat di salvare una copia locale del file Figma (File → **Save local copy…**) prima delle modifiche. È solo un consiglio: l'agente lavora sempre sul file Figma online e procede anche se la copia non viene fatta.

- **Modalità Operativa:** `WRITE-BOUNDED`. Modifica chirurgica limitata esclusivamente ai nodi approvati.
- **Ispezione Puntuale su Figma:**
  - L'agente legge solo i nodi indicati nella Colonna D (`ID Nodo Figma`). È vietato richiedere l'intero albero del file.

### Strumenti Figma consentiti (elenco chiuso)
Si usano **solo** questi strumenti del server MCP di Figma. Qualunque altro strumento Figma è vietato (es. `html_to_figma`, `send_code_to_figma`, `create_new_file`, `upload_assets`, `generate_*`).

| Strumento | Quando usarlo |
|---|---|
| `create_session` | Una volta, all'inizio, con il `fileKey` preso dal link. |
| `get_metadata` | Per trovare e verificare i nodi della Colonna D (esistenza, dimensioni prima/dopo la modifica). |
| `get_variable_defs` | Per il Livello 1 di minima invasività: scegliere la variabile/stile conforme più vicino. |
| `get_design_context` | Per leggere colori, padding e testi dei soli nodi approvati, prima e dopo la modifica. |
| `get_screenshot` | Facoltativo: controllo visivo del nodo dopo la modifica. |
| `use_figma` | **L'unico strumento che modifica il file.** Solo sui nodi delle voci approvate (Decisione `Accolta`/`Modificata` e Chi applica `Agente`/`Entrambi`), una voce alla volta, con i valori calcolati da `corrector.py` / `color_utils.py`. Mai per creare, spostare o eliminare nodi non coinvolti. |

Questo elenco è applicato anche dall'hook `skills/common/lib/figma_guard.py`, che blocca ogni altro strumento Figma mentre `/correzione` è attivo.
- **Gerarchia di Minima Invasività per Correzioni Grafiche:**
  1. *Livello 1 - Token di Progetto:* Se il progetto ha variabili colore o stili, applica il token conforme più vicino.
  2. *Livello 2 - Spaziature/Padding:* Per bottoni o icone sotto target, espande il padding secondo la formula deterministica di `color_utils.py`.
  3. *Livello 3 - Modulazione HLS a Tonalità Costante:* Per problemi di colore/contrasto, applica il valore esadecimale calcolato da `adjust_lightness_for_contrast`.
- **Annotazioni Tecniche Figma (Codice):**
  - Per difetti non correggibili visivamente su Figma (es. attributi ARIA, focus ring da tastiera, semantica HTML), inserisce un'annotazione per gli sviluppatori sul nodo Figma.

---

## 5. Comando di Esecuzione dello Script

Il file Excel resta nella sua cartella (quella con il nome del file Figma): lo script aggiorna lo stesso file.

L'agente esegue lo script deterministico `corrector.py`:

```bash
# Passo A: Verifica e visualizzazione delle decisioni approvate (Dry-Run):
<ROOT>/.venv/bin/python <ROOT>/skills/agente-correzione/scripts/corrector.py \
  --excel [percorso-report-audit.xlsx] \
  --demo

# Passo B: Scrittura Log Correzioni:
<ROOT>/.venv/bin/python <ROOT>/skills/agente-correzione/scripts/corrector.py \
  --excel [percorso-report-audit.xlsx] \
  --apply

# Opzionale: override dettagli log da JSON:
<ROOT>/.venv/bin/python <ROOT>/skills/agente-correzione/scripts/corrector.py \
  --excel [percorso-report-audit.xlsx] \
  --apply \
  --log-json override.json
```

---

## 6. Definizione OUTPUT

1. **Prototipo Figma Aggiornato:**
   - I singoli nodi autorizzati risultano modificati chirurgicamente (colori aggiornati, padding adattati, annotazioni codice inserite).
2. **File Excel di Audit AGGIORNATO (stesso file in input):**
   - **Foglio `Log Correzioni` (9 Colonne create/aggiornate):**
     - `1: ID Voce`
     - `2: ID Nodo Figma`
     - `3: Ambito` (Usabilità / Accessibilità)
     - `4: Riferimento` (WCAG / Nielsen)
     - `5: Elemento`
     - `6: Azione Eseguita` (dettaglio della correzione applicata su Figma)
     - `7: Annotazione / Codice Applicato` (prescrizione tecnica W3C ARIA/HTML)
     - `8: Esito` (`Risolto` / `Annotato`)
     - `9: Verifica Post-Intervento` (rapporto di contrasto post-modifica o dimensioni verificate)
   - **Foglio `Voci`:** Colonna W (`Data della decisione`) popolata automaticamente con la data odierna se lasciata vuota.
- **Notifica Finale:** riepilogo per l'utente dei nodi modificati su Figma, conferma dell'avvenuto aggiornamento del file Excel.

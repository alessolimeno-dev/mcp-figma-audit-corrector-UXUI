---
name: agente-correzione
description: Applica sul prototipo Figma le correzioni approvate dal progettista nel report Excel (WRITE-BOUNDED) con il principio di minima invasività e compila il foglio Log Correzioni.
---

# Skill: Agente di Correzione UI/UX (Fase 2)

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

### Passo 0 — Copia locale del file Figma (obbligatorio, bloccante)
Prima di qualunque modifica su Figma, l'agente scrive in chat:
> *"Prima di procedere con le modifiche, salva una copia locale del file Figma: in Figma apri il file → menu File → **Save local copy…** e conserva il file `.fig` (ad esempio nella cartella del report). Rispondimi quando hai fatto."*

e **non modifica alcun nodo** finché l'utente non conferma di aver salvato la copia (o dichiara esplicitamente di volerne fare a meno).

- **Modalità Operativa:** `WRITE-BOUNDED`. Modifica chirurgica limitata esclusivamente ai nodi approvati.
- **Ispezione Puntuale su Figma:**
  - L'agente richiede via MCP (`get_node` / nodi mirati) solo i nodi indicati nella Colonna D (`ID Nodo Figma`). È vietato richiedere l'intero albero del file.
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
